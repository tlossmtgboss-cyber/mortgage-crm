"""
Document Data Extractor Service

AI-powered extraction of structured data from mortgage documents.
Supports all document types with type-specific extraction schemas.

Uses Claude API for intelligent extraction with confidence scoring
and provenance tracking.
"""

import json
import logging
import os
import re
import time
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, field

try:
    from anthropic import Anthropic
    HAS_ANTHROPIC = True
except ImportError:
    HAS_ANTHROPIC = False

try:
    import pytesseract
    from PIL import Image
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

from models.smart_docs_models import DocType
from services.smart_docs.ai_resilience import resilient_ai_call

logger = logging.getLogger(__name__)


# =============================================================================
# EXTRACTION SCHEMAS BY DOCUMENT TYPE
# =============================================================================

EXTRACTION_SCHEMAS = {
    DocType.PAYSTUB: {
        "description": "Pay stub / earnings statement",
        "fields": {
            # === EMPLOYER INFORMATION ===
            "employer_name": {"type": "string", "category": "employment", "lead_field": "employer_name"},
            "employer_address_line1": {"type": "string", "category": "employment", "lead_field": None},
            "employer_address_line2": {"type": "string", "category": "employment", "lead_field": None},
            "employer_city": {"type": "string", "category": "employment", "lead_field": None},
            "employer_state": {"type": "string", "category": "employment", "lead_field": None},
            "employer_zip": {"type": "string", "category": "employment", "lead_field": None},
            "employer_phone": {"type": "string", "category": "employment", "lead_field": None},
            "employer_ein": {"type": "string", "category": "employment", "lead_field": None},

            # === EMPLOYEE INFORMATION ===
            "employee_name": {"type": "string", "category": "identity", "lead_field": None},
            "employee_address_line1": {"type": "string", "category": "identity", "lead_field": None},
            "employee_address_line2": {"type": "string", "category": "identity", "lead_field": None},
            "employee_city": {"type": "string", "category": "identity", "lead_field": None},
            "employee_state": {"type": "string", "category": "identity", "lead_field": None},
            "employee_zip": {"type": "string", "category": "identity", "lead_field": None},
            "employee_ssn_last4": {"type": "string", "category": "identity", "lead_field": None},
            "employee_id": {"type": "string", "category": "identity", "lead_field": None},
            "hire_date": {"type": "date", "category": "employment", "lead_field": None},

            # === PAY PERIOD INFORMATION ===
            "pay_period_start": {"type": "date", "category": "dates", "lead_field": None},
            "pay_period_end": {"type": "date", "category": "dates", "lead_field": None},
            "pay_date": {"type": "date", "category": "dates", "lead_field": None},
            "pay_frequency": {"type": "enum", "category": "employment", "lead_field": None,
                              "values": ["weekly", "biweekly", "semimonthly", "monthly"]},

            # === CURRENT PERIOD EARNINGS ===
            "gross_pay": {"type": "currency", "category": "income", "lead_field": None},
            "net_pay": {"type": "currency", "category": "income", "lead_field": None},
            "regular_hours": {"type": "number", "category": "income", "lead_field": None},
            "overtime_hours": {"type": "number", "category": "income", "lead_field": None},
            "hourly_rate": {"type": "currency", "category": "income", "lead_field": None},
            "regular_earnings": {"type": "currency", "category": "income", "lead_field": None},
            "overtime_earnings": {"type": "currency", "category": "income", "lead_field": None},
            "bonus": {"type": "currency", "category": "income", "lead_field": None},
            "commission": {"type": "currency", "category": "income", "lead_field": None},
            "tips": {"type": "currency", "category": "income", "lead_field": None},
            "other_earnings": {"type": "currency", "category": "income", "lead_field": None},

            # === YEAR-TO-DATE TOTALS ===
            "ytd_gross": {"type": "currency", "category": "income", "lead_field": None},
            "ytd_net": {"type": "currency", "category": "income", "lead_field": None},
            "ytd_regular_earnings": {"type": "currency", "category": "income", "lead_field": None},
            "ytd_overtime_earnings": {"type": "currency", "category": "income", "lead_field": None},
            "ytd_bonus": {"type": "currency", "category": "income", "lead_field": None},
            "ytd_commission": {"type": "currency", "category": "income", "lead_field": None},
            "ytd_tips": {"type": "currency", "category": "income", "lead_field": None},

            # === CURRENT PERIOD DEDUCTIONS ===
            "federal_tax": {"type": "currency", "category": "deductions", "lead_field": None},
            "state_tax": {"type": "currency", "category": "deductions", "lead_field": None},
            "local_tax": {"type": "currency", "category": "deductions", "lead_field": None},
            "social_security": {"type": "currency", "category": "deductions", "lead_field": None},
            "medicare": {"type": "currency", "category": "deductions", "lead_field": None},
            "health_insurance": {"type": "currency", "category": "deductions", "lead_field": None},
            "dental_insurance": {"type": "currency", "category": "deductions", "lead_field": None},
            "vision_insurance": {"type": "currency", "category": "deductions", "lead_field": None},
            "life_insurance": {"type": "currency", "category": "deductions", "lead_field": None},
            "retirement_401k": {"type": "currency", "category": "deductions", "lead_field": None},
            "hsa_fsa": {"type": "currency", "category": "deductions", "lead_field": None},
            "other_deductions": {"type": "currency", "category": "deductions", "lead_field": None},

            # === YTD DEDUCTIONS ===
            "ytd_federal_tax": {"type": "currency", "category": "deductions", "lead_field": None},
            "ytd_state_tax": {"type": "currency", "category": "deductions", "lead_field": None},
            "ytd_social_security": {"type": "currency", "category": "deductions", "lead_field": None},
            "ytd_medicare": {"type": "currency", "category": "deductions", "lead_field": None},
            "ytd_retirement": {"type": "currency", "category": "deductions", "lead_field": None},
        },
        "calculated_fields": {
            "annual_income": {
                "formula": "Calculate from YTD or extrapolate from period pay",
                "lead_field": "annual_income"
            },
            "monthly_income": {
                "formula": "Annual income / 12",
                "lead_field": None
            }
        }
    },

    DocType.W2: {
        "description": "W-2 Wage and Tax Statement",
        "fields": {
            "employee_name": {"type": "string", "category": "identity", "lead_field": None},
            "employee_ssn_last4": {"type": "string", "category": "identity", "lead_field": None},
            "employer_name": {"type": "string", "category": "employment", "lead_field": "employer_name"},
            "employer_ein": {"type": "string", "category": "employment", "lead_field": None},
            "employer_address": {"type": "string", "category": "employment", "lead_field": None},
            "tax_year": {"type": "integer", "category": "tax", "lead_field": None},
            "wages_tips_compensation": {"type": "currency", "category": "income", "lead_field": "annual_income"},
            "federal_tax_withheld": {"type": "currency", "category": "tax", "lead_field": None},
            "social_security_wages": {"type": "currency", "category": "income", "lead_field": None},
            "medicare_wages": {"type": "currency", "category": "income", "lead_field": None},
            "state": {"type": "string", "category": "tax", "lead_field": None},
            "state_wages": {"type": "currency", "category": "income", "lead_field": None},
            "state_tax_withheld": {"type": "currency", "category": "tax", "lead_field": None},
        }
    },

    DocType.BANK_STATEMENT: {
        "description": "Bank account statement",
        "fields": {
            "account_holder_name": {"type": "string", "category": "identity", "lead_field": None},
            "bank_name": {"type": "string", "category": "assets", "lead_field": None},
            "account_number_last4": {"type": "string", "category": "assets", "lead_field": None},
            "account_type": {"type": "enum", "category": "assets", "lead_field": None,
                            "values": ["checking", "savings", "money_market", "cd"]},
            "statement_start_date": {"type": "date", "category": "dates", "lead_field": None},
            "statement_end_date": {"type": "date", "category": "dates", "lead_field": None},
            "beginning_balance": {"type": "currency", "category": "assets", "lead_field": None},
            "ending_balance": {"type": "currency", "category": "assets", "lead_field": None},
            "average_balance": {"type": "currency", "category": "assets", "lead_field": None},
            "total_deposits": {"type": "currency", "category": "assets", "lead_field": None},
            "total_withdrawals": {"type": "currency", "category": "assets", "lead_field": None},
        }
    },

    DocType.DRIVERS_LICENSE: {
        "description": "Driver's license or state ID",
        "fields": {
            "full_name": {"type": "string", "category": "identity", "lead_field": None},
            "first_name": {"type": "string", "category": "identity", "lead_field": "first_name"},
            "last_name": {"type": "string", "category": "identity", "lead_field": "last_name"},
            "middle_name": {"type": "string", "category": "identity", "lead_field": None},
            "date_of_birth": {"type": "date", "category": "identity", "lead_field": None},
            "address": {"type": "string", "category": "address", "lead_field": "address"},
            "city": {"type": "string", "category": "address", "lead_field": "city"},
            "state": {"type": "string", "category": "address", "lead_field": "state"},
            "zip_code": {"type": "string", "category": "address", "lead_field": "zip_code"},
            "license_number": {"type": "string", "category": "identity", "lead_field": None},
            "issue_date": {"type": "date", "category": "dates", "lead_field": None},
            "expiration_date": {"type": "date", "category": "dates", "lead_field": None},
            "sex": {"type": "string", "category": "identity", "lead_field": None},
        }
    },

    DocType.TAX_RETURN: {
        "description": "Personal tax return (Form 1040)",
        "fields": {
            "taxpayer_name": {"type": "string", "category": "identity", "lead_field": None},
            "spouse_name": {"type": "string", "category": "identity", "lead_field": None},
            "tax_year": {"type": "integer", "category": "tax", "lead_field": None},
            "filing_status": {"type": "enum", "category": "tax", "lead_field": None,
                             "values": ["single", "married_filing_jointly", "married_filing_separately",
                                       "head_of_household", "qualifying_widow"]},
            "total_income": {"type": "currency", "category": "income", "lead_field": None},
            "adjusted_gross_income": {"type": "currency", "category": "income", "lead_field": "annual_income"},
            "taxable_income": {"type": "currency", "category": "income", "lead_field": None},
            "total_tax": {"type": "currency", "category": "tax", "lead_field": None},
            "refund_amount": {"type": "currency", "category": "tax", "lead_field": None},
            "amount_owed": {"type": "currency", "category": "tax", "lead_field": None},
        }
    },

    DocType.INVESTMENT_STATEMENT: {
        "description": "Investment or brokerage account statement",
        "fields": {
            "account_holder_name": {"type": "string", "category": "identity", "lead_field": None},
            "institution_name": {"type": "string", "category": "assets", "lead_field": None},
            "account_number_last4": {"type": "string", "category": "assets", "lead_field": None},
            "account_type": {"type": "enum", "category": "assets", "lead_field": None,
                            "values": ["brokerage", "ira", "401k", "roth_ira", "sep_ira", "other"]},
            "statement_date": {"type": "date", "category": "dates", "lead_field": None},
            "total_account_value": {"type": "currency", "category": "assets", "lead_field": None},
            "cash_balance": {"type": "currency", "category": "assets", "lead_field": None},
        }
    },

    DocType.PROFIT_LOSS: {
        "description": "Profit and Loss statement for self-employed",
        "fields": {
            "business_name": {"type": "string", "category": "employment", "lead_field": "employer_name"},
            "owner_name": {"type": "string", "category": "identity", "lead_field": None},
            "period_start": {"type": "date", "category": "dates", "lead_field": None},
            "period_end": {"type": "date", "category": "dates", "lead_field": None},
            "gross_revenue": {"type": "currency", "category": "income", "lead_field": None},
            "total_expenses": {"type": "currency", "category": "income", "lead_field": None},
            "net_profit": {"type": "currency", "category": "income", "lead_field": None},
        }
    },

    DocType.PURCHASE_CONTRACT: {
        "description": "Real estate purchase contract",
        "fields": {
            "buyer_name": {"type": "string", "category": "identity", "lead_field": None},
            "seller_name": {"type": "string", "category": "identity", "lead_field": None},
            "property_address": {"type": "string", "category": "address", "lead_field": "address"},
            "property_city": {"type": "string", "category": "address", "lead_field": "city"},
            "property_state": {"type": "string", "category": "address", "lead_field": "state"},
            "property_zip": {"type": "string", "category": "address", "lead_field": "zip_code"},
            "purchase_price": {"type": "currency", "category": "income", "lead_field": None},
            "earnest_money": {"type": "currency", "category": "income", "lead_field": None},
            "closing_date": {"type": "date", "category": "dates", "lead_field": None},
            "contract_date": {"type": "date", "category": "dates", "lead_field": None},
        }
    },
}

# Default schema for document types not specifically defined
DEFAULT_EXTRACTION_SCHEMA = {
    "description": "Generic document",
    "fields": {
        "document_date": {"type": "date", "category": "dates", "lead_field": None},
        "names_found": {"type": "string_array", "category": "identity", "lead_field": None},
        "addresses_found": {"type": "string_array", "category": "address", "lead_field": None},
        "amounts_found": {"type": "currency_array", "category": "income", "lead_field": None},
    }
}


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class ExtractionResult:
    """Result of document data extraction."""
    success: bool
    extracted_fields: Dict[str, Any] = field(default_factory=dict)
    confidence_scores: Dict[str, int] = field(default_factory=dict)  # 0-100
    provenance: Dict[str, str] = field(default_factory=dict)  # field -> source snippet
    mappable_fields: List[str] = field(default_factory=list)
    field_categories: Dict[str, str] = field(default_factory=dict)
    detected_names: List[str] = field(default_factory=list)
    overall_confidence: int = 0
    error: Optional[str] = None
    extraction_model: str = ""
    extraction_duration_ms: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "extracted_fields": self.extracted_fields,
            "confidence_scores": self.confidence_scores,
            "provenance": self.provenance,
            "mappable_fields": self.mappable_fields,
            "field_categories": self.field_categories,
            "detected_names": self.detected_names,
            "overall_confidence": self.overall_confidence,
            "error": self.error,
            "extraction_model": self.extraction_model,
            "extraction_duration_ms": self.extraction_duration_ms,
        }


# =============================================================================
# DOCUMENT DATA EXTRACTOR SERVICE
# =============================================================================

class DocumentDataExtractor:
    """
    Service for extracting structured data from mortgage documents.

    Uses Claude API for intelligent extraction with:
    - Type-specific extraction schemas
    - Confidence scoring per field
    - Provenance tracking (source text snippets)
    - Name detection for owner matching
    """

    def __init__(self):
        self.anthropic = Anthropic() if HAS_ANTHROPIC else None
        self.model = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6")

    def extract(
        self,
        file_content: bytes,
        mime_type: str,
        doc_type: Optional[DocType] = None,
        ocr_text: Optional[str] = None,
    ) -> ExtractionResult:
        """
        Extract structured data from a document.

        Args:
            file_content: Raw file bytes
            mime_type: MIME type of the file
            doc_type: Document type (if known)
            ocr_text: Pre-extracted OCR text (optional)

        Returns:
            ExtractionResult with extracted fields and metadata
        """
        start_time = time.time()

        try:
            # Get or extract text
            if ocr_text:
                text = ocr_text
            else:
                text = self._extract_text(file_content, mime_type)

            if not text or len(text) < 50:
                return ExtractionResult(
                    success=False,
                    error="Insufficient text extracted from document"
                )

            # Get extraction schema
            schema = EXTRACTION_SCHEMAS.get(doc_type, DEFAULT_EXTRACTION_SCHEMA)

            # Call LLM for extraction
            result = self._extract_with_llm(text, schema, doc_type)

            # Calculate duration
            duration_ms = int((time.time() - start_time) * 1000)
            result.extraction_duration_ms = duration_ms
            result.extraction_model = self.model

            return result

        except Exception as e:
            logger.exception(f"Extraction failed: {e}")
            return ExtractionResult(
                success=False,
                error=str(e),
                extraction_duration_ms=int((time.time() - start_time) * 1000)
            )

    def _extract_text(self, file_content: bytes, mime_type: str) -> str:
        """Extract text from file content."""
        if mime_type == "application/pdf":
            return self._extract_text_from_pdf(file_content)
        elif mime_type.startswith("image/"):
            return self._extract_text_from_image(file_content)
        else:
            # Try to decode as text
            try:
                return file_content.decode("utf-8")
            except Exception as e:
                logger.exception(f"Failed to decode file content as UTF-8: {e}")
                return ""

    def _extract_text_from_pdf(self, file_content: bytes) -> str:
        """Extract text from PDF using pdfplumber with OCR fallback."""
        text = ""

        # Try native text extraction first
        if HAS_PDFPLUMBER:
            try:
                import io
                with pdfplumber.open(io.BytesIO(file_content)) as pdf:
                    for page in pdf.pages[:10]:  # Limit to first 10 pages
                        page_text = page.extract_text() or ""
                        text += page_text + "\n"
            except Exception as e:
                logger.warning(f"pdfplumber extraction failed: {e}")

        # If insufficient text, try OCR
        if len(text.strip()) < 100 and HAS_PDF2IMAGE and HAS_TESSERACT:
            try:
                images = convert_from_bytes(file_content, first_page=1, last_page=5)
                for img in images:
                    ocr_text = pytesseract.image_to_string(img)
                    text += ocr_text + "\n"
            except Exception as e:
                logger.warning(f"OCR extraction failed: {e}")

        return text[:50000]  # Limit text length

    def _extract_text_from_image(self, file_content: bytes) -> str:
        """Extract text from image using OCR."""
        if not HAS_TESSERACT:
            return ""

        try:
            import io
            img = Image.open(io.BytesIO(file_content))
            return pytesseract.image_to_string(img)
        except Exception as e:
            logger.warning(f"Image OCR failed: {e}")
            return ""

    def _extract_with_llm(
        self,
        text: str,
        schema: Dict,
        doc_type: Optional[DocType]
    ) -> ExtractionResult:
        """Use Claude to extract structured data from text."""

        if not self.anthropic:
            return ExtractionResult(
                success=False,
                error="Anthropic API not available"
            )

        # Build field descriptions for the prompt
        field_descriptions = []
        for field_name, field_info in schema.get("fields", {}).items():
            field_type = field_info.get("type", "string")
            values = field_info.get("values", [])
            desc = f"- {field_name} ({field_type})"
            if values:
                desc += f" - one of: {', '.join(values)}"
            field_descriptions.append(desc)

        fields_str = "\n".join(field_descriptions)

        prompt = f"""You are a document data extraction expert. Extract structured data from this {schema.get('description', 'document')}.

DOCUMENT TEXT:
{text[:30000]}

FIELDS TO EXTRACT:
{fields_str}

INSTRUCTIONS:
1. Extract each field value if present in the document
2. For each field, also note the exact source text snippet where you found the value (for provenance)
3. Assign a confidence score (0-100) for each extracted value based on clarity and certainty
4. Extract ALL names found in the document (for owner matching)
5. For dates, use ISO format (YYYY-MM-DD)
6. For currency, extract as numbers without formatting (e.g., 50000.00 not $50,000.00)

RESPONSE FORMAT (JSON):
{{
    "extracted_fields": {{
        "field_name": "extracted value",
        ...
    }},
    "confidence_scores": {{
        "field_name": 85,
        ...
    }},
    "provenance": {{
        "field_name": "source text snippet showing where value was found",
        ...
    }},
    "detected_names": ["Name One", "Name Two", ...],
    "overall_confidence": 80
}}

Respond with ONLY the JSON object, no additional text."""

        try:
            response = resilient_ai_call(
                client=self.anthropic,
                model=self.model,
                max_tokens=4096,
                messages=[{"role": "user", "content": prompt}],
                operation_name="extract_document_data",
            )

            if response is None:
                return ExtractionResult(
                    success=False,
                    error="AI call failed after retries or circuit breaker open",
                )

            response_text = response.content[0].text.strip()

            # Parse JSON response
            # Handle potential markdown code blocks
            if response_text.startswith("```"):
                response_text = re.sub(r'^```json?\n?', '', response_text)
                response_text = re.sub(r'\n?```$', '', response_text)

            data = json.loads(response_text)

            # Build mappable fields list
            mappable_fields = []
            field_categories = {}

            for field_name, field_info in schema.get("fields", {}).items():
                if field_info.get("lead_field"):
                    mappable_fields.append(field_name)
                if field_info.get("category"):
                    field_categories[field_name] = field_info["category"]

            # Handle calculated fields
            if "calculated_fields" in schema:
                for calc_field, calc_info in schema["calculated_fields"].items():
                    if calc_info.get("lead_field"):
                        mappable_fields.append(calc_field)

                    # Calculate annual income from paystub data
                    if calc_field == "annual_income":
                        annual = self._calculate_annual_income(data.get("extracted_fields", {}))
                        if annual:
                            data["extracted_fields"]["annual_income"] = annual
                            data["confidence_scores"]["annual_income"] = 70  # Lower confidence for calculated
                            field_categories["annual_income"] = "income"

            return ExtractionResult(
                success=True,
                extracted_fields=data.get("extracted_fields", {}),
                confidence_scores=data.get("confidence_scores", {}),
                provenance=data.get("provenance", {}),
                mappable_fields=mappable_fields,
                field_categories=field_categories,
                detected_names=data.get("detected_names", []),
                overall_confidence=data.get("overall_confidence", 50),
            )

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse LLM response: {e}")
            return ExtractionResult(
                success=False,
                error=f"Failed to parse extraction response: {e}"
            )
        except Exception as e:
            logger.exception(f"LLM extraction failed: {e}")
            return ExtractionResult(
                success=False,
                error=str(e)
            )

    def _calculate_annual_income(self, fields: Dict) -> Optional[float]:
        """
        Calculate annual income from extracted paystub fields.

        IMPORTANT: For paystubs, gross_pay is the PAY PERIOD amount, not annual.
        We MUST annualize based on pay frequency:
        - Weekly: gross_pay × 52
        - Biweekly: gross_pay × 26
        - Semimonthly: gross_pay × 24
        - Monthly: gross_pay × 12

        YTD is only useful for validation or when we have multiple pay periods.
        """
        gross_pay = fields.get("gross_pay")
        pay_frequency = fields.get("pay_frequency", "").lower()
        ytd_gross = fields.get("ytd_gross")

        # Pay frequency multipliers for annualization
        multipliers = {
            "weekly": 52,
            "biweekly": 26,
            "semimonthly": 24,
            "monthly": 12,
        }

        # PRIMARY METHOD: Use gross_pay × frequency multiplier
        # This is the most accurate for paystubs
        if gross_pay:
            multiplier = multipliers.get(pay_frequency, 12)  # Default to monthly if unknown
            annualized = float(gross_pay) * multiplier

            # If we have YTD and it's significantly different, log a warning
            # but still use the period-based calculation
            if ytd_gross:
                ytd_float = float(ytd_gross)
                # If YTD is much larger than current period, the employee has been
                # working longer - but we still annualize the current period rate
                logger.debug(
                    f"Paystub annualization: gross_pay={gross_pay}, "
                    f"frequency={pay_frequency}, multiplier={multiplier}, "
                    f"annualized={annualized}, ytd_gross={ytd_gross}"
                )

            return annualized

        # FALLBACK: If no gross_pay but we have YTD, try to estimate
        # This is less accurate but better than nothing
        if ytd_gross:
            # Try to estimate how many pay periods have passed
            # based on pay_period_end date
            pay_period_end = fields.get("pay_period_end")
            if pay_period_end:
                try:
                    from datetime import datetime
                    period_end = datetime.strptime(pay_period_end, "%Y-%m-%d")
                    year_start = datetime(period_end.year, 1, 1)
                    days_elapsed = (period_end - year_start).days + 1

                    if days_elapsed > 0:
                        # Annualize YTD based on days elapsed
                        annualized = (float(ytd_gross) / days_elapsed) * 365
                        logger.debug(
                            f"YTD annualization fallback: ytd_gross={ytd_gross}, "
                            f"days_elapsed={days_elapsed}, annualized={annualized}"
                        )
                        return annualized
                except (ValueError, TypeError) as e:
                    logger.warning(f"Failed to parse pay_period_end for YTD annualization: {e}")

            # Last resort: assume YTD represents roughly this many months
            # This is very rough and not recommended
            logger.warning("Using raw YTD as annual income - not recommended")
            return float(ytd_gross)

        return None

    def extract_paystub_for_income(
        self,
        file_content: bytes,
        mime_type: str,
        ocr_text: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Extract comprehensive paystub data for income tracking system.

        Returns a dictionary structured for the PaystubExtraction model with:
        - All extracted fields
        - Calculated annual/monthly income
        - Expiration date based on pay frequency
        - Confidence scores and extraction metadata
        """
        from datetime import date, timedelta

        result = self.extract(
            file_content=file_content,
            mime_type=mime_type,
            doc_type=DocType.PAYSTUB,
            ocr_text=ocr_text,
        )

        if not result.success:
            return {
                "success": False,
                "error": result.error,
                "extraction_model": self.model,
            }

        fields = result.extracted_fields
        confidences = result.confidence_scores

        # Calculate expiration date based on pay frequency
        pay_frequency = fields.get("pay_frequency", "").upper()
        pay_date_str = fields.get("pay_date")

        expiration_days = {
            "WEEKLY": 7,
            "BIWEEKLY": 30,
            "SEMIMONTHLY": 30,
            "MONTHLY": 45,
        }

        expires_at = None
        if pay_date_str:
            try:
                # Parse pay date (should be ISO format YYYY-MM-DD)
                pay_date = datetime.strptime(pay_date_str, "%Y-%m-%d").date()
                days_until_expire = expiration_days.get(pay_frequency, 30)
                expires_at = pay_date + timedelta(days=days_until_expire)
            except (ValueError, TypeError):
                # If pay date parsing fails, use document date + 30 days
                expires_at = date.today() + timedelta(days=30)

        # Calculate annual and monthly income
        annual_income = self._calculate_annual_income(fields)
        monthly_income = annual_income / 12 if annual_income else None

        # Structure for PaystubExtraction model
        paystub_data = {
            "success": True,

            # Employer info
            "employer_name": fields.get("employer_name"),
            "employer_address_line1": fields.get("employer_address_line1"),
            "employer_address_line2": fields.get("employer_address_line2"),
            "employer_city": fields.get("employer_city"),
            "employer_state": fields.get("employer_state"),
            "employer_zip": fields.get("employer_zip"),
            "employer_phone": fields.get("employer_phone"),
            "employer_ein": fields.get("employer_ein"),

            # Employee info
            "employee_name": fields.get("employee_name"),
            "employee_address_line1": fields.get("employee_address_line1"),
            "employee_address_line2": fields.get("employee_address_line2"),
            "employee_city": fields.get("employee_city"),
            "employee_state": fields.get("employee_state"),
            "employee_zip": fields.get("employee_zip"),
            "employee_ssn_last4": fields.get("employee_ssn_last4"),
            "employee_id": fields.get("employee_id"),
            "hire_date": fields.get("hire_date"),

            # Pay period
            "pay_period_start": fields.get("pay_period_start"),
            "pay_period_end": fields.get("pay_period_end"),
            "pay_date": pay_date_str,
            "pay_frequency": pay_frequency if pay_frequency else None,

            # Current earnings
            "gross_pay": self._safe_decimal(fields.get("gross_pay")),
            "net_pay": self._safe_decimal(fields.get("net_pay")),
            "regular_hours": self._safe_decimal(fields.get("regular_hours")),
            "overtime_hours": self._safe_decimal(fields.get("overtime_hours")),
            "hourly_rate": self._safe_decimal(fields.get("hourly_rate")),
            "regular_earnings": self._safe_decimal(fields.get("regular_earnings")),
            "overtime_earnings": self._safe_decimal(fields.get("overtime_earnings")),
            "bonus": self._safe_decimal(fields.get("bonus")),
            "commission": self._safe_decimal(fields.get("commission")),
            "tips": self._safe_decimal(fields.get("tips")),
            "other_earnings": self._safe_decimal(fields.get("other_earnings")),

            # YTD totals
            "ytd_gross": self._safe_decimal(fields.get("ytd_gross")),
            "ytd_net": self._safe_decimal(fields.get("ytd_net")),
            "ytd_regular_earnings": self._safe_decimal(fields.get("ytd_regular_earnings")),
            "ytd_overtime_earnings": self._safe_decimal(fields.get("ytd_overtime_earnings")),
            "ytd_bonus": self._safe_decimal(fields.get("ytd_bonus")),
            "ytd_commission": self._safe_decimal(fields.get("ytd_commission")),
            "ytd_tips": self._safe_decimal(fields.get("ytd_tips")),

            # Deductions
            "federal_tax": self._safe_decimal(fields.get("federal_tax")),
            "state_tax": self._safe_decimal(fields.get("state_tax")),
            "local_tax": self._safe_decimal(fields.get("local_tax")),
            "social_security": self._safe_decimal(fields.get("social_security")),
            "medicare": self._safe_decimal(fields.get("medicare")),
            "health_insurance": self._safe_decimal(fields.get("health_insurance")),
            "dental_insurance": self._safe_decimal(fields.get("dental_insurance")),
            "vision_insurance": self._safe_decimal(fields.get("vision_insurance")),
            "life_insurance": self._safe_decimal(fields.get("life_insurance")),
            "retirement_401k": self._safe_decimal(fields.get("retirement_401k")),
            "hsa_fsa": self._safe_decimal(fields.get("hsa_fsa")),
            "other_deductions": self._safe_decimal(fields.get("other_deductions")),

            # YTD Deductions
            "ytd_federal_tax": self._safe_decimal(fields.get("ytd_federal_tax")),
            "ytd_state_tax": self._safe_decimal(fields.get("ytd_state_tax")),
            "ytd_social_security": self._safe_decimal(fields.get("ytd_social_security")),
            "ytd_medicare": self._safe_decimal(fields.get("ytd_medicare")),
            "ytd_retirement": self._safe_decimal(fields.get("ytd_retirement")),

            # Calculated fields
            "calculated_annual_income": annual_income,
            "calculated_monthly_income": monthly_income,
            "annualization_method": "ytd_extrapolation" if fields.get("ytd_gross") else "period_multiplier",

            # Freshness
            "doc_date": pay_date_str,
            "expires_at": expires_at.isoformat() if expires_at else None,
            "is_expired": expires_at < date.today() if expires_at else False,

            # Extraction metadata
            "extraction_confidence": result.overall_confidence,
            "field_confidences": confidences,
            "extraction_model": self.model,
            "extraction_duration_ms": result.extraction_duration_ms,
            "detected_names": result.detected_names,
            "extraction_warnings": [],
        }

        # Add warnings for missing critical fields
        if not fields.get("employer_name"):
            paystub_data["extraction_warnings"].append("Employer name not found")
        if not fields.get("gross_pay") and not fields.get("ytd_gross"):
            paystub_data["extraction_warnings"].append("No income amounts found")
        if not pay_date_str:
            paystub_data["extraction_warnings"].append("Pay date not found - using current date for expiration")

        return paystub_data

    def _safe_decimal(self, value: Any) -> Optional[float]:
        """Safely convert a value to float, returning None if invalid."""
        if value is None:
            return None
        try:
            # Handle string values with currency formatting
            if isinstance(value, str):
                value = value.replace("$", "").replace(",", "").strip()
                if not value:
                    return None
            return float(value)
        except (ValueError, TypeError):
            return None


# =============================================================================
# PAY FREQUENCY EXPIRATION MAPPING
# =============================================================================

PAY_FREQUENCY_EXPIRATION_DAYS = {
    "WEEKLY": 7,
    "BIWEEKLY": 30,
    "SEMIMONTHLY": 30,
    "MONTHLY": 45,
}


# Singleton instance
_extractor_instance = None


def get_document_data_extractor() -> DocumentDataExtractor:
    """Get the singleton extractor instance."""
    global _extractor_instance
    if _extractor_instance is None:
        _extractor_instance = DocumentDataExtractor()
    return _extractor_instance
