"""
Identity Extraction Agent

Extracts borrower identity information from call transcripts.
"""

import re
from typing import List, Dict, Any
import logging

from .base_agent import BaseExtractionAgent
from ..data_contracts import (
    TranscriptSegment,
    ExtractionResult,
    ExtractedValue,
)

logger = logging.getLogger(__name__)


class IdentityExtractionAgent(BaseExtractionAgent):
    """Agent for extracting identity information."""

    AGENT_NAME = "identity"
    AGENT_VERSION = "2.0"  # LLM-first extraction
    EXTRACTION_SCHEMA_KEY = "identity"

    async def extract(
        self,
        segments: List[TranscriptSegment],
        existing_data: Dict[str, Any] = None,
    ) -> ExtractionResult:
        """
        Extract identity fields from transcript.

        Uses LLM extraction as primary method with regex fallback.
        """
        # Try LLM extraction first
        llm_result = await self.extract_with_llm(segments, existing_data)

        # Always run regex as fallback/validation
        regex_result = self.extract_with_regex(segments, existing_data)

        # Merge results, preferring LLM when available
        return self.merge_results(llm_result, regex_result)

    def extract_with_regex(
        self,
        segments: List[TranscriptSegment],
        existing_data: Dict[str, Any] = None,
    ) -> ExtractionResult:
        """Fallback regex-based extraction for identity fields."""
        result = ExtractionResult(agent_name=self.AGENT_NAME)

        borrower_text = self.get_borrower_text(segments)
        full_text = self.get_full_text(segments)

        # Extract name
        name_extraction = self._extract_name(borrower_text, full_text)
        if name_extraction:
            result.extractions.extend(name_extraction)

        # Extract SSN
        ssn = self._extract_ssn(borrower_text)
        if ssn:
            result.extractions.append(ssn)

        # Extract DOB
        dob = self._extract_dob(borrower_text, full_text)
        if dob:
            result.extractions.append(dob)

        # Extract email
        email = self.extract_email(borrower_text)
        if email:
            result.extractions.append(email)

        # Extract phone
        phone = self.extract_phone(borrower_text)
        if phone:
            result.extractions.append(phone)

        # Extract citizenship
        citizenship = self._extract_citizenship(borrower_text, full_text)
        if citizenship:
            result.extractions.append(citizenship)

        # Extract marital status
        marital = self._extract_marital_status(borrower_text, full_text)
        if marital:
            result.extractions.append(marital)

        return result

    def _extract_name(
        self,
        borrower_text: str,
        full_text: str,
    ) -> List[ExtractedValue]:
        """Extract first and last name."""
        extractions = []

        # Pattern: "my name is [Name]" or "I'm [Name]"
        name_patterns = [
            r"(?:my name is|i'm|i am|this is)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)",
            r"(?:name is|call me)\s+([A-Z][a-z]+)",
        ]

        for pattern in name_patterns:
            match = re.search(pattern, borrower_text, re.IGNORECASE)
            if match:
                full_name = match.group(1).strip()
                parts = full_name.split()

                if len(parts) >= 1:
                    extractions.append(ExtractedValue(
                        field_name="first_name",
                        value=parts[0].title(),
                        confidence=85.0,
                        source_text=borrower_text[max(0, match.start()-20):match.end()+20],
                    ))

                if len(parts) >= 2:
                    extractions.append(ExtractedValue(
                        field_name="last_name",
                        value=parts[-1].title(),
                        confidence=85.0,
                        source_text=borrower_text[max(0, match.start()-20):match.end()+20],
                    ))

                break

        # Look for verification patterns in AI speech
        verify_patterns = [
            r"(?:confirm|verify|spell).*?(?:first name|name).*?([A-Z][a-z]+)",
            r"(?:last name).*?([A-Z][a-z]+)",
        ]

        return extractions

    def _extract_ssn(self, text: str) -> ExtractedValue:
        """Extract SSN (last 4 digits only for security)."""
        patterns = [
            r"(?:social|ssn|social security).*?(\d{4})",
            r"(?:last four|last 4).*?(\d{4})",
            r"(\d{3}[-\s]?\d{2}[-\s]?\d{4})",  # Full SSN
        ]

        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                ssn = match.group(1).replace('-', '').replace(' ', '')

                # Only store last 4
                if len(ssn) == 9:
                    ssn = ssn[-4:]

                if len(ssn) == 4 and ssn.isdigit():
                    return ExtractedValue(
                        field_name="ssn",
                        value=ssn,
                        confidence=90.0,
                        source_text="[SSN redacted]",
                    )
        return None

    def _extract_dob(
        self,
        borrower_text: str,
        full_text: str,
    ) -> ExtractedValue:
        """Extract date of birth."""
        patterns = [
            r"(?:born|birthday|birth date|date of birth|dob).*?(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",
            r"(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}).*?(?:born|birthday|birth)",
        ]

        for pattern in patterns:
            match = re.search(pattern, full_text, re.IGNORECASE)
            if match:
                return ExtractedValue(
                    field_name="date_of_birth",
                    value=match.group(1),
                    confidence=85.0,
                    source_text=full_text[max(0, match.start()-30):match.end()+30],
                )

        # Also try month name format
        month_pattern = r"(?:born|birthday).*?((?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4})"
        match = re.search(month_pattern, full_text, re.IGNORECASE)
        if match:
            return ExtractedValue(
                field_name="date_of_birth",
                value=match.group(1),
                confidence=85.0,
                source_text=full_text[max(0, match.start()-30):match.end()+30],
            )

        return None

    def _extract_citizenship(
        self,
        borrower_text: str,
        full_text: str,
    ) -> ExtractedValue:
        """Extract citizenship status."""
        # US Citizen
        citizen_patterns = [
            r"(?:i am|i'm|yes,?\s+i'm).*?(?:us|u\.s\.|american|united states)\s*citizen",
            r"(?:citizen|citizenship).*?(?:yes|us|u\.s\.|united states)",
            r"born in (?:the\s+)?(?:us|u\.s\.|united states|america)",
        ]

        for pattern in citizen_patterns:
            if re.search(pattern, full_text, re.IGNORECASE):
                return ExtractedValue(
                    field_name="citizenship_status",
                    value="US_CITIZEN",
                    confidence=85.0,
                    source_text=full_text[:200],
                )

        # Permanent Resident
        pr_patterns = [
            r"(?:permanent resident|green card|legal resident)",
            r"(?:i have|i've got).*?green card",
        ]

        for pattern in pr_patterns:
            if re.search(pattern, full_text, re.IGNORECASE):
                return ExtractedValue(
                    field_name="citizenship_status",
                    value="PERMANENT_RESIDENT",
                    confidence=80.0,
                    source_text=full_text[:200],
                )

        return None

    def _extract_marital_status(
        self,
        borrower_text: str,
        full_text: str,
    ) -> ExtractedValue:
        """Extract marital status."""
        status_map = {
            "MARRIED": [r"\b(?:married|spouse|wife|husband)\b"],
            "SINGLE": [r"\b(?:single|unmarried|not married)\b"],
            "DIVORCED": [r"\b(?:divorced|ex-wife|ex-husband)\b"],
            "SEPARATED": [r"\bseparated\b"],
            "WIDOWED": [r"\b(?:widowed|widow|widower)\b"],
        }

        for status, patterns in status_map.items():
            for pattern in patterns:
                if re.search(pattern, full_text, re.IGNORECASE):
                    return ExtractedValue(
                        field_name="marital_status",
                        value=status,
                        confidence=80.0,
                        source_text=full_text[:200],
                    )

        return None
