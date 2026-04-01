"""
Identity Extraction Agent

Extracts borrower identity information from call transcripts.

SECURITY NOTE:
- SSN extraction only returns last 4 digits
- Full SSNs are never stored, logged, or transmitted
- All source_text fields are sanitized to remove PII
"""

import re
from typing import List, Dict, Any
import logging

from .base_agent import BaseExtractionAgent, ConfidenceScores
from .shared_patterns import (
    US_CITIZEN_PATTERNS_COMPILED,
    PERMANENT_RESIDENT_PATTERNS_COMPILED,
    MARITAL_STATUS_PATTERNS,
)
from ..data_contracts import (
    TranscriptSegment,
    ExtractionResult,
    ExtractedValue,
)
from ..pii_utils import (
    extract_ssn_last_four,
    sanitize_source_text,
    contains_ssn,
)

logger = logging.getLogger(__name__)


class IdentityExtractionAgent(BaseExtractionAgent):
    """Agent for extracting identity information."""

    AGENT_NAME = "identity"
    AGENT_VERSION = "2.0"  # LLM-first extraction
    RECOMMENDED_MODEL = "haiku"  # Simple structured data extraction (name, DOB, contact)
    EXTRACTION_SCHEMA_KEY = "identity"

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

                # Sanitize source text to remove any PII
                raw_source = borrower_text[max(0, match.start()-20):match.end()+20]
                safe_source = sanitize_source_text(raw_source)

                if len(parts) >= 1:
                    extractions.append(ExtractedValue(
                        field_name="first_name",
                        value=parts[0].title(),
                        confidence=ConfidenceScores.REGEX_HIGH,
                        source_text=safe_source,
                        extraction_method="regex",
                    ))

                if len(parts) >= 2:
                    extractions.append(ExtractedValue(
                        field_name="last_name",
                        value=parts[-1].title(),
                        confidence=ConfidenceScores.REGEX_HIGH,
                        source_text=safe_source,
                        extraction_method="regex",
                    ))

                break

        # Look for verification patterns in AI speech
        verify_patterns = [
            r"(?:confirm|verify|spell).*?(?:first name|name).*?([A-Z][a-z]+)",
            r"(?:last name).*?([A-Z][a-z]+)",
        ]

        return extractions

    def _extract_ssn(self, text: str) -> ExtractedValue:
        """
        Securely extract SSN last 4 digits only.

        SECURITY: This method uses pii_utils to ensure:
        - Full SSN is NEVER stored in any variable longer than necessary
        - Only last 4 digits are extracted and returned
        - Source text is always redacted
        - If full SSN is detected, a warning is logged (without the SSN)
        """
        # Use secure extraction that never exposes full SSN
        last_four, full_ssn_detected = extract_ssn_last_four(text)

        if last_four:
            # Log security warning if full SSN was in transcript
            # (but do NOT log the actual SSN)
            if full_ssn_detected:
                logger.warning(
                    "Full SSN detected in transcript - only last 4 digits extracted. "
                    "Consider advising borrowers not to state full SSN."
                )

            # Higher confidence if we detected a full SSN vs just last 4 digits
            return ExtractedValue(
                field_name="ssn_last_four",
                value=last_four,
                confidence=ConfidenceScores.REGEX_HIGH if full_ssn_detected else ConfidenceScores.REGEX_MEDIUM,
                source_text="[SSN redacted for security]",
                extraction_method="regex",
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
                raw_source = full_text[max(0, match.start()-30):match.end()+30]
                return ExtractedValue(
                    field_name="date_of_birth",
                    value=match.group(1),
                    confidence=ConfidenceScores.REGEX_HIGH,
                    source_text=sanitize_source_text(raw_source),
                    extraction_method="regex",
                )

        # Also try month name format
        month_pattern = r"(?:born|birthday).*?((?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4})"
        match = re.search(month_pattern, full_text, re.IGNORECASE)
        if match:
            raw_source = full_text[max(0, match.start()-30):match.end()+30]
            return ExtractedValue(
                field_name="date_of_birth",
                value=match.group(1),
                confidence=ConfidenceScores.REGEX_HIGH,
                source_text=sanitize_source_text(raw_source),
                extraction_method="regex",
            )

        return None

    def _extract_citizenship(
        self,
        borrower_text: str,
        full_text: str,
    ) -> ExtractedValue:
        """Extract citizenship status using shared patterns."""
        # US Citizen - use shared compiled patterns
        for pattern in US_CITIZEN_PATTERNS_COMPILED:
            match = pattern.search(full_text)
            if match:
                raw_source = full_text[max(0, match.start()-20):match.end()+20]
                return ExtractedValue(
                    field_name="citizenship_status",
                    value="US_CITIZEN",
                    confidence=ConfidenceScores.REGEX_HIGH,
                    source_text=sanitize_source_text(raw_source),
                    extraction_method="regex",
                )

        # Permanent Resident
        for pattern in PERMANENT_RESIDENT_PATTERNS_COMPILED:
            match = pattern.search(full_text)
            if match:
                raw_source = full_text[max(0, match.start()-20):match.end()+20]
                return ExtractedValue(
                    field_name="citizenship_status",
                    value="PERMANENT_RESIDENT",
                    confidence=ConfidenceScores.REGEX_MEDIUM,
                    source_text=sanitize_source_text(raw_source),
                    extraction_method="regex",
                )

        return None

    def _extract_marital_status(
        self,
        borrower_text: str,
        full_text: str,
    ) -> ExtractedValue:
        """Extract marital status using shared patterns."""
        for status, patterns in MARITAL_STATUS_PATTERNS.items():
            for pattern in patterns:
                match = pattern.search(full_text)
                if match:
                    raw_source = full_text[max(0, match.start()-20):match.end()+20]
                    return ExtractedValue(
                        field_name="marital_status",
                        value=status,
                        confidence=ConfidenceScores.REGEX_MEDIUM,
                        source_text=sanitize_source_text(raw_source),
                        extraction_method="regex",
                    )

        return None
