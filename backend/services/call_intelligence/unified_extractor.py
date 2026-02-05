"""
Unified Extraction Engine

Replaces 6 parallel LLM calls with a single unified extraction call.
This provides ~6x reduction in API calls and costs while maintaining
extraction quality.

Features:
- Single LLM call extracts all domains at once
- Unified schema combining identity, property, employment, financial,
  compliance, and intent extractions
- Maintains confidence scoring and source text tracking
- Compatible with existing data contracts
"""

import logging
import hashlib
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .llm_client import BaseLLMClient

from .data_contracts import (
    ExtractedValue,
    ExtractionResult,
    TranscriptSegment,
    SpeakerRole,
)
from .pii_utils import sanitize_source_text
from .llm_client import (
    ExtractionSchema,
    ExtractionField,
    EXTRACTION_SCHEMAS,
)

logger = logging.getLogger(__name__)


# =============================================================================
# Unified Schema Definition
# =============================================================================

def build_unified_schema() -> ExtractionSchema:
    """
    Build a unified schema combining all 6 extraction domains.

    This merges the schemas from:
    - Identity (borrower info)
    - Property (address, property details)
    - Employment (job info)
    - Financial (income, assets, liabilities)
    - Compliance (declarations)
    - Intent (loan purpose, preferences)
    """
    all_fields = []

    # Collect fields from all schemas with domain prefixes for clarity
    domain_schemas = [
        ("identity", EXTRACTION_SCHEMAS.get("identity")),
        ("property", EXTRACTION_SCHEMAS.get("property")),
        ("employment", EXTRACTION_SCHEMAS.get("employment")),
        ("financial", EXTRACTION_SCHEMAS.get("financial")),
        ("compliance", EXTRACTION_SCHEMAS.get("compliance")),
        ("intent", EXTRACTION_SCHEMAS.get("intent")),
    ]

    for domain, schema in domain_schemas:
        if schema:
            for field_def in schema.fields:
                # Create a copy with domain context
                all_fields.append(ExtractionField(
                    name=field_def.name,
                    description=f"[{domain.upper()}] {field_def.description}",
                    type=field_def.type,
                    required=field_def.required,
                    examples=field_def.examples,
                ))

    return ExtractionSchema(
        fields=all_fields,
        context="Mortgage loan application data extraction",
        instructions="""Extract ALL relevant information from this mortgage call transcript.

IMPORTANT GUIDELINES:
1. Only extract information explicitly stated by the BORROWER (not the loan officer)
2. If the borrower corrects themselves, use the corrected value
3. Handle speech disfluencies (um, uh, like) - extract the actual information
4. For unclear/ambiguous info, set confidence below 70
5. If a field is not mentioned, set value to null with confidence 0
6. For currency values, convert to numbers (e.g., "seventy thousand" -> 70000)
7. For dates, use ISO format (YYYY-MM-DD)
8. For yes/no questions, extract as boolean true/false

EXTRACTION CATEGORIES:
- IDENTITY: Name, SSN last 4, DOB, contact info, marital status, citizenship
- PROPERTY: Address, property type, purchase price, current housing
- EMPLOYMENT: Employer, job title, employment type, income
- FINANCIAL: Salary, assets, bank accounts, debts, liabilities
- COMPLIANCE: Bankruptcy, foreclosure, judgments, citizenship declarations
- INTENT: Loan purpose, timeline, preferences, urgency"""
    )


# Build the unified schema once at module load
UNIFIED_SCHEMA = build_unified_schema()


@dataclass
class UnifiedExtractionResult:
    """Result from unified extraction containing all domains."""

    call_id: str

    # Domain-specific extractions
    identity: Dict[str, ExtractedValue] = field(default_factory=dict)
    property_info: Dict[str, ExtractedValue] = field(default_factory=dict)  # Renamed from 'property' to avoid shadowing @property
    employment: Dict[str, ExtractedValue] = field(default_factory=dict)
    financial: Dict[str, ExtractedValue] = field(default_factory=dict)
    compliance: Dict[str, ExtractedValue] = field(default_factory=dict)
    intent: Dict[str, ExtractedValue] = field(default_factory=dict)

    # Metadata
    model_version: Optional[str] = None
    prompt_hash: Optional[str] = None
    processing_time_ms: int = 0
    llm_tokens_used: int = 0
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    @property
    def total_extractions(self) -> int:
        """Count total extractions across all domains."""
        return sum([
            len(self.identity),
            len(self.property_info),
            len(self.employment),
            len(self.financial),
            len(self.compliance),
            len(self.intent),
        ])

    @property
    def high_confidence_count(self) -> int:
        """Count extractions with confidence >= 90."""
        count = 0
        for domain in [self.identity, self.property_info, self.employment,
                       self.financial, self.compliance, self.intent]:
            for extraction in domain.values():
                if extraction.confidence >= 90:
                    count += 1
        return count

    @property
    def low_confidence_count(self) -> int:
        """Count extractions with confidence < 70."""
        count = 0
        for domain in [self.identity, self.property_info, self.employment,
                       self.financial, self.compliance, self.intent]:
            for extraction in domain.values():
                if extraction.confidence < 70:
                    count += 1
        return count

    def to_agent_results(self) -> List[ExtractionResult]:
        """Convert to list of ExtractionResult for backward compatibility."""
        results = []

        domain_mapping = [
            ("identity", self.identity),
            ("property", self.property_info),
            ("employment", self.employment),
            ("financial", self.financial),
            ("compliance", self.compliance),
            ("intent", self.intent),
        ]

        for agent_name, extractions in domain_mapping:
            result = ExtractionResult(agent_name=agent_name)
            result.extractions = list(extractions.values())
            result.warnings = self.warnings
            results.append(result)

        return results


# Field to domain mapping for categorization
FIELD_TO_DOMAIN = {}

# Identity fields
for field_name in ["first_name", "last_name", "middle_name", "suffix",
                   "ssn_last_four", "date_of_birth", "email", "phone",
                   "marital_status", "dependents", "citizenship_status"]:
    FIELD_TO_DOMAIN[field_name] = "identity"

# Property fields
for field_name in ["street_address", "city", "state", "zip_code",
                   "property_type", "purchase_price", "down_payment",
                   "down_payment_percent", "current_housing_status",
                   "current_housing_payment", "years_at_current_address"]:
    FIELD_TO_DOMAIN[field_name] = "property"

# Employment fields
for field_name in ["employer_name", "job_title", "employment_start_date",
                   "years_at_job", "employment_type", "is_self_employed",
                   "business_name", "industry", "employer_phone",
                   "employer_address", "previous_employer", "years_at_previous_job"]:
    FIELD_TO_DOMAIN[field_name] = "employment"

# Financial fields
for field_name in ["annual_salary", "monthly_salary", "hourly_rate",
                   "bonus_income", "commission_income", "overtime_income",
                   "rental_income", "other_income", "checking_balance",
                   "savings_balance", "retirement_balance", "investment_balance",
                   "gift_funds", "car_payment", "student_loan_payment",
                   "credit_card_payment", "other_debt_payment"]:
    FIELD_TO_DOMAIN[field_name] = "financial"

# Compliance fields
for field_name in ["has_bankruptcy", "bankruptcy_type", "bankruptcy_discharge_date",
                   "has_foreclosure", "foreclosure_date", "has_judgments",
                   "has_delinquent_debt", "is_party_to_lawsuit", "has_alimony",
                   "alimony_amount", "will_occupy_as_primary", "is_first_time_buyer",
                   "has_ownership_interest"]:
    FIELD_TO_DOMAIN[field_name] = "compliance"

# Intent fields
for field_name in ["loan_purpose", "loan_type_preference", "rate_type_preference",
                   "target_timeline", "urgency", "has_preapproval", "has_realtor",
                   "realtor_name", "has_property_identified", "competing_with_other_lenders"]:
    FIELD_TO_DOMAIN[field_name] = "intent"


class UnifiedExtractionEngine:
    """
    Single LLM call extracts all domains at once.

    This replaces the 6 parallel agent calls with a single unified extraction,
    providing ~6x reduction in API calls while maintaining extraction quality.
    """

    VERSION = "1.0"

    # Token limit for unified extraction response
    UNIFIED_MAX_TOKENS = 8000  # Increased from ~800 per agent

    def __init__(self, llm_client: "BaseLLMClient"):
        """
        Initialize unified extraction engine.

        Args:
            llm_client: LLM client for extraction (required)
        """
        if llm_client is None:
            raise ValueError("UnifiedExtractionEngine requires an LLM client")

        self.llm_client = llm_client
        self._schema = UNIFIED_SCHEMA
        self._prompt_hash = self._compute_prompt_hash()

    def _compute_prompt_hash(self) -> str:
        """Compute hash of prompt/schema for versioning."""
        schema_str = str([
            (f.name, f.description, f.type)
            for f in self._schema.fields
        ])
        return hashlib.sha256(schema_str.encode()).hexdigest()[:16]

    def _format_transcript(self, segments: List[TranscriptSegment]) -> str:
        """Format transcript segments for LLM processing."""
        role_names = {
            "ai_lo": "Loan Officer",
            "borrower": "Borrower",
            "co_borrower": "Co-Borrower",
            "human_lo": "Human Loan Officer",
            "unknown": "Unknown",
        }

        lines = []
        for segment in segments:
            speaker = segment.speaker.value if hasattr(segment.speaker, 'value') else str(segment.speaker)
            speaker_name = role_names.get(speaker.lower(), speaker)
            lines.append(f"{speaker_name}: {segment.text}")

        return "\n".join(lines)

    async def extract_all(
        self,
        call_id: str,
        segments: List[TranscriptSegment],
        existing_data: Optional[Dict[str, Any]] = None,
    ) -> UnifiedExtractionResult:
        """
        Extract all domains from transcript in a single API call.

        Args:
            call_id: Unique identifier for the call
            segments: Transcript segments
            existing_data: Optional existing borrower data for context

        Returns:
            UnifiedExtractionResult with all domain extractions
        """
        start_time = time.time()
        result = UnifiedExtractionResult(call_id=call_id)
        result.prompt_hash = self._prompt_hash

        if not segments:
            result.errors.append("No transcript segments provided")
            return result

        transcript = self._format_transcript(segments)

        try:
            logger.info(f"Running unified extraction for call {call_id}")

            # Call LLM with unified schema
            llm_response = await self.llm_client.extract(
                transcript=transcript,
                schema=self._schema,
                existing_data=existing_data,
            )

            # Parse and categorize response
            result = self._parse_unified_response(call_id, llm_response)
            result.prompt_hash = self._prompt_hash

            # Track processing time
            result.processing_time_ms = int((time.time() - start_time) * 1000)

            logger.info(
                f"Unified extraction for {call_id}: "
                f"{result.total_extractions} total extractions, "
                f"{result.high_confidence_count} high confidence, "
                f"{result.processing_time_ms}ms"
            )

            return result

        except Exception as e:
            logger.exception(f"Unified extraction failed for {call_id}: {e}")
            result.errors.append(str(e))
            result.processing_time_ms = int((time.time() - start_time) * 1000)
            return result

    def _parse_unified_response(
        self,
        call_id: str,
        response: Dict[str, Any],
    ) -> UnifiedExtractionResult:
        """
        Parse LLM response and categorize into domains.

        Args:
            call_id: Call identifier
            response: LLM response with extractions dict

        Returns:
            UnifiedExtractionResult with categorized extractions
        """
        result = UnifiedExtractionResult(call_id=call_id)

        extractions = response.get("extractions", {})
        notes = response.get("notes", "")

        if notes:
            result.warnings.append(notes)

        for field_name, field_data in extractions.items():
            # Determine which domain this field belongs to
            domain = FIELD_TO_DOMAIN.get(field_name, "identity")  # Default to identity

            # Parse field data
            if isinstance(field_data, dict):
                value = field_data.get("value")
                confidence = field_data.get("confidence", 0)
                source_text = field_data.get("source_text", "")

                # Skip null values with very low confidence
                if value is None and confidence < 10:
                    continue

                extracted = ExtractedValue(
                    field_name=field_name,
                    value=value,
                    confidence=float(confidence),
                    source_text=sanitize_source_text(source_text),
                    extraction_method="unified_llm",
                )
            else:
                # Simple value without metadata
                if field_data is None:
                    continue

                extracted = ExtractedValue(
                    field_name=field_name,
                    value=field_data,
                    confidence=75.0,  # Default confidence for simple values
                    extraction_method="unified_llm",
                )

            # Add to appropriate domain
            domain_dict = getattr(result, domain)
            domain_dict[field_name] = extracted

        return result

    def get_model_version_info(self) -> Dict[str, Any]:
        """Get version info for model tracking."""
        return {
            "engine_version": self.VERSION,
            "prompt_hash": self._prompt_hash,
            "schema_field_count": len(self._schema.fields),
            "max_tokens": self.UNIFIED_MAX_TOKENS,
        }


# =============================================================================
# Factory function
# =============================================================================

def create_unified_extractor(llm_client: "BaseLLMClient") -> UnifiedExtractionEngine:
    """
    Factory function to create unified extractor.

    Args:
        llm_client: LLM client (required)

    Returns:
        Configured UnifiedExtractionEngine
    """
    return UnifiedExtractionEngine(llm_client)
