"""
Base Extraction Agent

Abstract base class for all extraction agents with LLM-first extraction
and regex fallback.
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
import re
import logging

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

    def __init__(self, llm_client: BaseLLMClient = None):
        """
        Initialize agent with LLM client.

        Args:
            llm_client: LLM client for AI-powered extraction.
                       If None, will attempt to create one from env vars.
        """
        self._llm_client = llm_client
        self._llm_initialized = False

    @property
    def llm_client(self) -> Optional[BaseLLMClient]:
        """Lazy initialization of LLM client."""
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

    @abstractmethod
    async def extract(
        self,
        segments: List[TranscriptSegment],
        existing_data: Dict[str, Any] = None,
    ) -> ExtractionResult:
        """
        Extract data from transcript segments.

        Args:
            segments: List of transcript segments
            existing_data: Existing borrower data for context

        Returns:
            ExtractionResult with extracted values
        """
        pass

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
            logger.debug(f"Running LLM extraction for {self.AGENT_NAME}")

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
                    f"{len(result.extractions)} fields extracted"
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
            # Map speaker roles to readable names
            speaker_map = {
                'ai_lo': 'Loan Officer',
                'borrower': 'Borrower',
                'co_borrower': 'Co-Borrower',
                'human_lo': 'Human Loan Officer',
                'unknown': 'Unknown',
            }
            speaker_name = speaker_map.get(speaker.lower(), speaker)
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
                if value is None and confidence < 10:
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
                        confidence=75.0,  # Default confidence for simple values
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
        Merge LLM and regex results, preferring LLM when available.

        Strategy:
        - Use LLM values when confidence >= 70
        - Fall back to regex for fields LLM missed
        - Use regex to validate/boost LLM confidence when both match
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
                    llm_extraction.confidence = min(100, llm_extraction.confidence + 10)
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

        # Normalize numbers (within 1% tolerance)
        if isinstance(val1, (int, float)) and isinstance(val2, (int, float)):
            if val1 == 0 and val2 == 0:
                return True
            return abs(val1 - val2) / max(abs(val1), abs(val2)) < 0.01

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
        confidence_base: float = 75.0,
    ) -> Optional[ExtractedValue]:
        """Extract value using regex pattern."""
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            value = match.group(1).strip() if match.groups() else match.group(0).strip()
            raw_source = text[max(0, match.start()-50):match.end()+50]
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
                    confidence=70.0,
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
                    confidence=75.0,
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
                        confidence=90.0,
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
                confidence=95.0,
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
                    confidence=80.0,
                    source_text=sanitize_source_text(text[:200]),
                    verification_question=question_context,
                    extraction_method="regex",
                )

        for pattern in negative:
            if re.search(pattern, text, re.IGNORECASE):
                return ExtractedValue(
                    field_name=field_name,
                    value=False,
                    confidence=80.0,
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
        """Calculate final confidence score."""
        confidence = extraction.confidence

        if verified:
            confidence = min(100, confidence + 15)

        if multiple_mentions:
            confidence = min(100, confidence + 10)

        return confidence
