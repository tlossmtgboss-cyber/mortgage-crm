"""
Base Extraction Agent

Abstract base class for all extraction agents with LLM-first extraction
and regex fallback.
"""

from abc import ABC, abstractmethod
import logging
import re
import threading
from typing import Any, Dict, List, Optional

from ..data_contracts import (
    TranscriptSegment,
    ExtractionResult,
    ExtractedValue,
    SpeakerRole,
)
from ..pii_utils import sanitize_source_text
from ..llm_client import (
    BaseLLMClient,
    ExtractionSchema,
    EXTRACTION_SCHEMAS,
    create_llm_client,
)

logger = logging.getLogger(__name__)


# =============================================================================
# Confidence Score Constants
# =============================================================================
# These constants define confidence levels for different extraction scenarios.
# Scores range from 0-100, where:
#   90-100: High confidence - clear, unambiguous extraction
#   70-89:  Moderate confidence - likely correct but may need verification
#   50-69:  Low confidence - ambiguous, needs manual review
#   Below 50: Very low confidence - unreliable extraction

class ConfidenceScores:
    """Standardized confidence scores for extraction results."""

    # LLM extraction defaults
    LLM_HIGH = 90.0     # High certainty LLM extraction
    LLM_MEDIUM = 77.0   # Moderate certainty LLM extraction
    LLM_DEFAULT = 75.0  # Default for simple LLM values without confidence metadata
    LLM_LOW = 50.0      # Low certainty LLM extraction

    # Regex extraction defaults
    REGEX_HIGH = 90.0   # Clear pattern match (e.g., email, phone)
    REGEX_MEDIUM = 80.0 # Good pattern match
    REGEX_DEFAULT = 75.0  # Standard pattern match
    REGEX_LOW = 70.0    # Weak pattern match (e.g., currency without context)

    # Specific extraction types
    EMAIL = 95.0        # Email regex is highly reliable
    PHONE = 90.0        # Phone regex is reliable
    NAME = 85.0         # Name extraction
    DATE = 75.0         # Date extraction
    CURRENCY = 70.0     # Currency extraction (can be ambiguous)
    YES_NO = 80.0       # Boolean response extraction
    SSN_LAST_FOUR = 90.0  # SSN last 4 when full SSN detected
    SSN_PARTIAL = 85.0    # SSN last 4 from partial input

    # Confidence adjustments
    VERIFICATION_BOOST = 15   # Boost when value is verified by multiple sources
    MULTIPLE_MENTION_BOOST = 10  # Boost when mentioned multiple times
    LLM_REGEX_MATCH_BOOST = 10   # Boost when LLM and regex agree

    # Thresholds
    HIGH_CONFIDENCE_THRESHOLD = 90  # Above this is high confidence
    LOW_CONFIDENCE_THRESHOLD = 70   # Below this needs verification
    SKIP_THRESHOLD = 10             # Below this, skip null values

    # Extraction settings
    CONTEXT_WINDOW_SIZE = 50        # Characters to include before/after match for context
    NUMERIC_MATCH_TOLERANCE = 0.01  # 1% tolerance for numeric comparisons


class ValidationRanges:
    """Validation ranges for extracted values.

    These ranges define reasonable bounds for mortgage-related values
    to filter out obviously incorrect extractions.
    """

    # Income ranges (annual)
    MIN_ANNUAL_SALARY = 10_000      # $10K minimum
    MAX_ANNUAL_SALARY = 5_000_000   # $5M maximum

    # Income ranges (monthly)
    MIN_MONTHLY_SALARY = 1_000      # $1K minimum
    MAX_MONTHLY_SALARY = 500_000    # $500K maximum

    # Hourly rate
    MIN_HOURLY_RATE = 5.0           # $5/hr minimum
    MAX_HOURLY_RATE = 500.0         # $500/hr maximum

    # Property values
    MIN_PROPERTY_VALUE = 50_000     # $50K minimum
    MAX_PROPERTY_VALUE = 50_000_000 # $50M maximum

    # Down payment
    MIN_DOWN_PAYMENT = 1_000        # $1K minimum
    MIN_DOWN_PAYMENT_PERCENT = 1    # 1% minimum
    MAX_DOWN_PAYMENT_PERCENT = 100  # 100% maximum

    # Monthly payments (car, student loan, etc.)
    MIN_CAR_PAYMENT = 50            # $50/month minimum
    MAX_CAR_PAYMENT = 2_000         # $2K/month maximum

    # Asset balances
    MIN_ASSET_BALANCE = 100         # $100 minimum

    # Years of experience/employment
    MIN_YEARS = 0
    MAX_YEARS = 50


# =============================================================================
# Speaker Role Display Names
# =============================================================================
# Maps internal speaker role values to human-readable names for LLM prompts.
# Used in _format_transcript_for_llm() for clearer context.

SPEAKER_ROLE_DISPLAY_NAMES: Dict[str, str] = {
    'ai_lo': 'Loan Officer',
    'borrower': 'Borrower',
    'co_borrower': 'Co-Borrower',
    'human_lo': 'Human Loan Officer',
    'unknown': 'Unknown',
}
"""Maps SpeakerRole values to human-readable display names."""


# =============================================================================
# Numeric Comparison Constants
# =============================================================================

EPSILON = 1e-10
"""Small value for floating-point comparisons near zero."""


class BaseExtractionAgent(ABC):
    """
    Abstract base class for extraction agents.

    Each agent:
    1. Uses LLM extraction as primary method (accurate, handles natural language)
    2. Falls back to regex patterns (fast, works without API)
    3. Validates and normalizes extracted values
    4. Returns ExtractionResult with confidence scores

    Confidence scoring:
    - 90-100: LLM extraction with high certainty or multiple confirmations
    - 70-89: LLM extraction with moderate certainty or regex match
    - 50-69: Ambiguous extraction, needs verification
    - Below 50: Low confidence, likely needs manual review
    """

    AGENT_NAME: str = "base"
    AGENT_VERSION: str = "2.0"  # Version bump for LLM extraction

    # Override in subclasses to specify which schema to use
    EXTRACTION_SCHEMA_KEY: str = None

    # Override in subclasses to request a specific model tier.
    # "haiku" = fast/cheap model for simpler extraction (identity, employment)
    # "sonnet" = full model for complex extraction (financial, compliance)
    # None = use the default from LLMConfig/environment (currently claude-3-haiku)
    RECOMMENDED_MODEL: Optional[str] = None

    def __init__(self, llm_client: BaseLLMClient = None):
        """
        Initialize agent with LLM client.

        Args:
            llm_client: LLM client for AI-powered extraction.
                       If None, will attempt to create one from env vars.
        """
        self._llm_client = llm_client
        self._llm_initialized = False
        self._llm_lock = threading.Lock()  # Thread-safe lazy initialization

    @property
    def llm_client(self) -> Optional[BaseLLMClient]:
        """Lazy initialization of LLM client (thread-safe)."""
        if self._llm_client is None and not self._llm_initialized:
            with self._llm_lock:
                # Double-check after acquiring lock
                if self._llm_client is None and not self._llm_initialized:
                    self._llm_initialized = True
                    try:
                        self._llm_client = create_llm_client()
                        logger.info(f"LLM client initialized for {self.AGENT_NAME} agent")
                    except Exception as e:
                        logger.warning(f"Could not initialize LLM client: {e}. Using regex fallback.")
        return self._llm_client

    def get_extraction_schema(self) -> Optional[ExtractionSchema]:
        """Get the extraction schema for this agent."""
        if self.EXTRACTION_SCHEMA_KEY:
            return EXTRACTION_SCHEMAS.get(self.EXTRACTION_SCHEMA_KEY)
        return None

    async def extract(
        self,
        segments: List[TranscriptSegment],
        existing_data: Dict[str, Any] = None,
    ) -> ExtractionResult:
        """
        Extract data from transcript segments.

        Uses LLM extraction as primary method with regex fallback.
        Subclasses should implement extract_with_regex() for their
        domain-specific regex patterns.

        Args:
            segments: List of transcript segments
            existing_data: Existing borrower data for context

        Returns:
            ExtractionResult with extracted values
        """
        # Try LLM extraction first
        llm_result = await self.extract_with_llm(segments, existing_data)

        # Always run regex as fallback/validation
        regex_result = self.extract_with_regex(segments, existing_data)

        # Merge results, preferring LLM when available
        return self.merge_results(llm_result, regex_result)

    @abstractmethod
    def extract_with_regex(
        self,
        segments: List[TranscriptSegment],
        existing_data: Dict[str, Any] = None,
    ) -> ExtractionResult:
        """
        Fallback regex-based extraction.

        Implement in subclasses with pattern-based extraction logic.
        """
        pass

    async def extract_with_llm(
        self,
        segments: List[TranscriptSegment],
        existing_data: Dict[str, Any] = None,
    ) -> Optional[ExtractionResult]:
        """
        Primary LLM-based extraction.

        Uses the agent's extraction schema to extract structured data.

        Args:
            segments: Transcript segments
            existing_data: Existing data for context

        Returns:
            ExtractionResult if successful, None otherwise
        """
        if not self.llm_client:
            logger.debug(f"No LLM client available for {self.AGENT_NAME}")
            return None

        schema = self.get_extraction_schema()
        if not schema:
            logger.warning(f"No extraction schema defined for {self.AGENT_NAME}")
            return None

        # Combine segments into transcript
        transcript = self._format_transcript_for_llm(segments)

        try:
            # Log model info for observability
            model_info = getattr(self.llm_client, 'config', None)
            model_name = model_info.model if model_info else "unknown"
            logger.debug(
                f"Running LLM extraction for {self.AGENT_NAME} "
                f"(model={model_name}, recommended={self.RECOMMENDED_MODEL})"
            )

            # Call LLM extraction
            llm_response = await self.llm_client.extract(
                transcript=transcript,
                schema=schema,
                existing_data=existing_data,
            )

            # Parse LLM response into ExtractionResult
            result = self._parse_llm_response(llm_response)

            if result and result.extractions:
                logger.info(
                    f"LLM extraction for {self.AGENT_NAME}: "
                    f"{len(result.extractions)} fields extracted "
                    f"(model={model_name})"
                )
                return result

            return None

        except Exception as e:
            logger.warning(f"LLM extraction failed for {self.AGENT_NAME}: {e}")
            return None

    def _format_transcript_for_llm(self, segments: List[TranscriptSegment]) -> str:
        """Format transcript segments for LLM processing."""
        lines = []
        for segment in segments:
            speaker = segment.speaker.value if hasattr(segment.speaker, 'value') else str(segment.speaker)
            # Map speaker roles to readable names using module constant
            speaker_name = SPEAKER_ROLE_DISPLAY_NAMES.get(speaker.lower(), speaker)
            lines.append(f"{speaker_name}: {segment.text}")
        return "\n".join(lines)

    def _parse_llm_response(self, response: Dict[str, Any]) -> Optional[ExtractionResult]:
        """
        Parse LLM response into ExtractionResult.

        Args:
            response: LLM response with 'extractions' dict

        Returns:
            ExtractionResult with extracted values
        """
        result = ExtractionResult(agent_name=self.AGENT_NAME)

        extractions = response.get("extractions", {})
        notes = response.get("notes", "")

        if notes:
            result.warnings.append(notes)

        for field_name, field_data in extractions.items():
            if isinstance(field_data, dict):
                value = field_data.get("value")
                confidence = field_data.get("confidence", 0)
                raw_source_text = field_data.get("source_text", "")

                # Skip null values with low confidence
                if value is None and confidence < ConfidenceScores.SKIP_THRESHOLD:
                    continue

                # Create ExtractedValue with sanitized source text
                extracted = ExtractedValue(
                    field_name=field_name,
                    value=value,
                    confidence=float(confidence),
                    source_text=sanitize_source_text(raw_source_text),
                    extraction_method="llm",
                )

                result.extractions.append(extracted)
            else:
                # Simple value without metadata
                if field_data is not None:
                    result.extractions.append(ExtractedValue(
                        field_name=field_name,
                        value=field_data,
                        confidence=ConfidenceScores.LLM_DEFAULT,
                        extraction_method="llm",
                    ))

        return result if result.extractions else None

    # -------------------------------------------------------------------------
    # Helper Methods (shared by all agents)
    # -------------------------------------------------------------------------

    def get_borrower_segments(
        self,
        segments: List[TranscriptSegment],
    ) -> List[TranscriptSegment]:
        """Get only borrower speech segments."""
        return [s for s in segments if s.speaker == SpeakerRole.BORROWER]

    def get_ai_segments(
        self,
        segments: List[TranscriptSegment],
    ) -> List[TranscriptSegment]:
        """Get only AI/Agent speech segments."""
        return [s for s in segments if s.speaker == SpeakerRole.AI_LO]

    def get_full_text(self, segments: List[TranscriptSegment]) -> str:
        """Combine all segments into full text."""
        return " ".join(s.text for s in segments)

    def get_borrower_text(self, segments: List[TranscriptSegment]) -> str:
        """Get combined borrower speech."""
        return " ".join(s.text for s in self.get_borrower_segments(segments))

    def find_segments_matching(
        self,
        segments: List[TranscriptSegment],
        patterns: List[str],
    ) -> List[TranscriptSegment]:
        """Find segments matching any of the patterns."""
        matching = []
        for segment in segments:
            for pattern in patterns:
                if re.search(pattern, segment.text, re.IGNORECASE):
                    matching.append(segment)
                    break
        return matching

    def merge_results(
        self,
        llm_result: Optional[ExtractionResult],
        regex_result: ExtractionResult,
    ) -> ExtractionResult:
        """
        Merge LLM and regex extraction results intelligently.

        This method combines results from LLM-based extraction (primary) and
        regex-based extraction (fallback) to produce the best possible output.

        Merge Strategy:
        1. If no LLM result, return regex result as-is
        2. For each field extracted by LLM:
           a. If regex also found the same field with matching value:
              - Boost LLM confidence by LLM_REGEX_MATCH_BOOST (10 points)
              - Mark as verified=True
           b. If regex found same field but values differ:
              - Use whichever has higher confidence
           c. If only LLM found it: use LLM value
        3. For fields only found by regex (LLM missed):
           - Add to results with extraction_method="regex_fallback"

        Confidence Boosting:
        - When LLM and regex agree on a value, confidence is boosted by
          ConfidenceScores.LLM_REGEX_MATCH_BOOST (typically 10 points)
        - Confidence is capped at 100

        Value Matching:
        - Strings: case-insensitive comparison after stripping whitespace
        - Numbers: within NUMERIC_MATCH_TOLERANCE (1% by default)
        - Other types: direct equality comparison

        Args:
            llm_result: Extraction result from LLM (may be None if LLM failed)
            regex_result: Extraction result from regex patterns

        Returns:
            ExtractionResult with merged extractions and combined warnings
        """
        if not llm_result:
            return regex_result

        merged = ExtractionResult(agent_name=self.AGENT_NAME)
        merged.warnings = llm_result.warnings + regex_result.warnings

        # Index regex results by field name
        regex_by_field = {e.field_name: e for e in regex_result.extractions}

        # Start with LLM results
        seen_fields = set()
        for llm_extraction in llm_result.extractions:
            field_name = llm_extraction.field_name
            seen_fields.add(field_name)

            # Check if regex found the same field
            regex_extraction = regex_by_field.get(field_name)

            if regex_extraction:
                # Both found it - compare and potentially boost confidence
                if self._values_match(llm_extraction.value, regex_extraction.value):
                    # Values match - boost confidence
                    llm_extraction.confidence = min(100, llm_extraction.confidence + ConfidenceScores.LLM_REGEX_MATCH_BOOST)
                    llm_extraction.verified = True
                elif llm_extraction.confidence < regex_extraction.confidence:
                    # Regex is more confident - use regex
                    merged.extractions.append(regex_extraction)
                    continue

            merged.extractions.append(llm_extraction)

        # Add regex results for fields LLM missed
        for regex_extraction in regex_result.extractions:
            if regex_extraction.field_name not in seen_fields:
                regex_extraction.extraction_method = "regex_fallback"
                merged.extractions.append(regex_extraction)

        return merged

    def _values_match(self, val1: Any, val2: Any) -> bool:
        """Check if two extracted values match (with normalization)."""
        if val1 is None or val2 is None:
            return False

        # Normalize strings
        if isinstance(val1, str) and isinstance(val2, str):
            return val1.lower().strip() == val2.lower().strip()

        # Normalize numbers (within tolerance defined by NUMERIC_MATCH_TOLERANCE)
        if isinstance(val1, (int, float)) and isinstance(val2, (int, float)):
            max_abs = max(abs(val1), abs(val2))
            # Handle near-zero values with epsilon comparison
            if max_abs < EPSILON:
                return abs(val1 - val2) < EPSILON
            return abs(val1 - val2) / max_abs < ConfidenceScores.NUMERIC_MATCH_TOLERANCE

        # Direct comparison
        return val1 == val2

    # -------------------------------------------------------------------------
    # Regex Extraction Helpers (used by subclass implementations)
    # -------------------------------------------------------------------------

    def extract_with_pattern(
        self,
        text: str,
        pattern: str,
        field_name: str,
        confidence_base: float = None,
    ) -> Optional[ExtractedValue]:
        """Extract value using regex pattern.

        Args:
            text: Text to search in
            pattern: Regex pattern with capture group
            field_name: Name of the field being extracted
            confidence_base: Base confidence score (defaults to REGEX_DEFAULT)

        Returns:
            ExtractedValue if pattern matches, None otherwise
        """
        if confidence_base is None:
            confidence_base = ConfidenceScores.REGEX_DEFAULT

        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            value = match.group(1).strip() if match.groups() else match.group(0).strip()
            window = ConfidenceScores.CONTEXT_WINDOW_SIZE
            raw_source = text[max(0, match.start() - window):match.end() + window]
            return ExtractedValue(
                field_name=field_name,
                value=value,
                confidence=confidence_base,
                source_text=sanitize_source_text(raw_source),
                extraction_method="regex",
            )
        return None

    def extract_currency(
        self,
        text: str,
        field_name: str,
        patterns: List[str] = None,
    ) -> Optional[ExtractedValue]:
        """Extract currency value from text."""
        if patterns is None:
            patterns = [
                r'\$[\d,]+(?:\.\d{2})?',
                r'(?:about|around|roughly|approximately)?\s*\$?(\d{1,3}(?:,\d{3})*(?:\.\d{2})?)\s*(?:dollars?)?',
                r'(\d+(?:\.\d{2})?)\s*(?:dollars?|bucks?)',
                r'(\d+)k',  # e.g., "100k"
                # Handle written numbers
                r'(?:seventy|eighty|ninety|hundred).*?thousand',
            ]

        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                value_str = match.group(1) if match.groups() else match.group(0)
                value_str = value_str.replace('$', '').replace(',', '').strip()

                # Handle "k" suffix
                if 'k' in text[match.start():match.end()+5].lower():
                    try:
                        value = float(value_str) * 1000
                    except ValueError:
                        continue
                else:
                    try:
                        value = float(value_str)
                    except ValueError:
                        continue

                raw_source = text[max(0, match.start()-30):match.end()+30]
                return ExtractedValue(
                    field_name=field_name,
                    value=value,
                    confidence=ConfidenceScores.CURRENCY,
                    source_text=sanitize_source_text(raw_source),
                    extraction_method="regex",
                )
        return None

    def extract_date(
        self,
        text: str,
        field_name: str,
    ) -> Optional[ExtractedValue]:
        """Extract date from text."""
        patterns = [
            # MM/DD/YYYY or MM-DD-YYYY
            r'(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})',
            # Month DD, YYYY
            r'((?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4})',
            # Month YYYY
            r'((?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4})',
        ]

        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                raw_source = text[max(0, match.start()-20):match.end()+20]
                return ExtractedValue(
                    field_name=field_name,
                    value=match.group(1),
                    confidence=ConfidenceScores.DATE,
                    source_text=sanitize_source_text(raw_source),
                    extraction_method="regex",
                )
        return None

    def extract_phone(
        self,
        text: str,
        field_name: str = "phone",
    ) -> Optional[ExtractedValue]:
        """Extract phone number from text."""
        patterns = [
            r'(\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4})',
            r'(\d{3}[-.\s]\d{3}[-.\s]\d{4})',
        ]

        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                phone = re.sub(r'[^\d]', '', match.group(1))
                if len(phone) == 10:
                    raw_source = text[max(0, match.start()-20):match.end()+20]
                    return ExtractedValue(
                        field_name=field_name,
                        value=phone,
                        confidence=ConfidenceScores.PHONE,
                        source_text=sanitize_source_text(raw_source),
                        extraction_method="regex",
                    )
        return None

    def extract_email(
        self,
        text: str,
        field_name: str = "email",
    ) -> Optional[ExtractedValue]:
        """Extract email from text."""
        pattern = r'([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})'
        match = re.search(pattern, text)
        if match:
            raw_source = text[max(0, match.start()-20):match.end()+20]
            return ExtractedValue(
                field_name=field_name,
                value=match.group(1).lower(),
                confidence=ConfidenceScores.EMAIL,
                source_text=sanitize_source_text(raw_source),
                extraction_method="regex",
            )
        return None

    def extract_yes_no(
        self,
        text: str,
        field_name: str,
        question_context: str = "",
    ) -> Optional[ExtractedValue]:
        """Extract yes/no response from text."""
        # Look for affirmative responses
        affirmative = [
            r'\b(?:yes|yeah|yep|yup|correct|right|affirmative|true|absolutely|definitely)\b',
            r'\bi do\b',
            r'\bi have\b',
            r'\bi am\b',
            r'\bthat\'s right\b',
        ]

        # Look for negative responses
        negative = [
            r'\b(?:no|nope|nah|negative|false|never)\b',
            r'\bi don\'t\b',
            r'\bi haven\'t\b',
            r'\bi\'m not\b',
            r'\bnot really\b',
        ]

        for pattern in affirmative:
            if re.search(pattern, text, re.IGNORECASE):
                return ExtractedValue(
                    field_name=field_name,
                    value=True,
                    confidence=ConfidenceScores.YES_NO,
                    source_text=sanitize_source_text(text[:200]),
                    verification_question=question_context,
                    extraction_method="regex",
                )

        for pattern in negative:
            if re.search(pattern, text, re.IGNORECASE):
                return ExtractedValue(
                    field_name=field_name,
                    value=False,
                    confidence=ConfidenceScores.YES_NO,
                    source_text=sanitize_source_text(text[:200]),
                    verification_question=question_context,
                    extraction_method="regex",
                )

        return None

    def calculate_confidence(
        self,
        extraction: ExtractedValue,
        verified: bool = False,
        multiple_mentions: bool = False,
    ) -> float:
        """Calculate final confidence score with standardized adjustments."""
        confidence = extraction.confidence

        if verified:
            confidence = min(100, confidence + ConfidenceScores.VERIFICATION_BOOST)

        if multiple_mentions:
            confidence = min(100, confidence + ConfidenceScores.MULTIPLE_MENTION_BOOST)

        return confidence
