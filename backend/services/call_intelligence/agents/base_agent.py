"""
Base Extraction Agent

Abstract base class for all extraction agents.
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

logger = logging.getLogger(__name__)


class BaseExtractionAgent(ABC):
    """
    Abstract base class for extraction agents.

    Each agent:
    1. Analyzes relevant transcript segments
    2. Extracts specific fields using patterns and/or LLM
    3. Calculates confidence scores
    4. Returns ExtractionResult
    """

    AGENT_NAME: str = "base"
    AGENT_VERSION: str = "1.0"

    def __init__(self, llm_client=None):
        """
        Initialize agent with optional LLM client.

        Args:
            llm_client: LLM client for AI-powered extraction
        """
        self.llm_client = llm_client

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

    # -------------------------------------------------------------------------
    # Helper Methods
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

    def extract_with_pattern(
        self,
        text: str,
        pattern: str,
        field_name: str,
        confidence_base: float = 80.0,
    ) -> Optional[ExtractedValue]:
        """Extract value using regex pattern."""
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            value = match.group(1).strip() if match.groups() else match.group(0).strip()
            return ExtractedValue(
                field_name=field_name,
                value=value,
                confidence=confidence_base,
                source_text=text[max(0, match.start()-50):match.end()+50],
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
                    except:
                        continue
                else:
                    try:
                        value = float(value_str)
                    except:
                        continue

                return ExtractedValue(
                    field_name=field_name,
                    value=value,
                    confidence=75.0,
                    source_text=text[max(0, match.start()-30):match.end()+30],
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
                return ExtractedValue(
                    field_name=field_name,
                    value=match.group(1),
                    confidence=80.0,
                    source_text=text[max(0, match.start()-20):match.end()+20],
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
                    return ExtractedValue(
                        field_name=field_name,
                        value=phone,
                        confidence=90.0,
                        source_text=text[max(0, match.start()-20):match.end()+20],
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
            return ExtractedValue(
                field_name=field_name,
                value=match.group(1).lower(),
                confidence=95.0,
                source_text=text[max(0, match.start()-20):match.end()+20],
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
        ]

        for pattern in affirmative:
            if re.search(pattern, text, re.IGNORECASE):
                return ExtractedValue(
                    field_name=field_name,
                    value=True,
                    confidence=85.0,
                    source_text=text[:200],
                    verification_question=question_context,
                )

        for pattern in negative:
            if re.search(pattern, text, re.IGNORECASE):
                return ExtractedValue(
                    field_name=field_name,
                    value=False,
                    confidence=85.0,
                    source_text=text[:200],
                    verification_question=question_context,
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

    async def extract_with_llm(
        self,
        prompt: str,
        text: str,
    ) -> Optional[Dict[str, Any]]:
        """Use LLM for complex extraction."""
        if not self.llm_client:
            return None

        try:
            # This would call the actual LLM API
            # For now, return None to fall back to pattern matching
            return None
        except Exception as e:
            logger.warning(f"LLM extraction failed: {e}")
            return None
