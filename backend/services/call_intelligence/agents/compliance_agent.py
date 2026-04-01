"""
Compliance Extraction Agent

Extracts declaration and compliance information from call transcripts.
"""

import logging
import re
from typing import Any, Dict, List

from .base_agent import BaseExtractionAgent, ConfidenceScores
from .shared_patterns import (
    US_CITIZEN_PATTERNS_COMPILED,
    PERMANENT_RESIDENT_PATTERNS_COMPILED,
    NON_PERMANENT_RESIDENT_PATTERNS_COMPILED,
)
from ..data_contracts import (
    TranscriptSegment,
    ExtractionResult,
    ExtractedValue,
)
from ..pii_utils import sanitize_source_text

logger = logging.getLogger(__name__)


class ComplianceExtractionAgent(BaseExtractionAgent):
    """Agent for extracting compliance/declaration information."""

    AGENT_NAME = "compliance"
    AGENT_VERSION = "2.0"  # LLM-first extraction
    EXTRACTION_SCHEMA_KEY = "compliance"
    RECOMMENDED_MODEL = "sonnet"  # Regulatory compliance needs precise reasoning

    def extract_with_regex(
        self,
        segments: List[TranscriptSegment],
        existing_data: Dict[str, Any] = None,
    ) -> ExtractionResult:
        """Fallback regex-based extraction for compliance fields."""
        result = ExtractionResult(agent_name=self.AGENT_NAME)

        borrower_text = self.get_borrower_text(segments)
        full_text = self.get_full_text(segments)

        # Extract citizenship
        citizenship = self._extract_citizenship(borrower_text, full_text)
        if citizenship:
            result.extractions.append(citizenship)

        # Extract bankruptcy
        bankruptcy = self._extract_bankruptcy(borrower_text, full_text)
        result.extractions.extend(bankruptcy)

        # Extract foreclosure
        foreclosure = self._extract_foreclosure(borrower_text, full_text)
        if foreclosure:
            result.extractions.append(foreclosure)

        # Extract judgments
        judgments = self._extract_judgments(borrower_text, full_text)
        if judgments:
            result.extractions.append(judgments)

        # Extract occupancy intent
        occupancy = self._extract_occupancy(borrower_text, full_text)
        if occupancy:
            result.extractions.append(occupancy)

        # Extract first-time buyer
        first_time = self._extract_first_time_buyer(borrower_text, full_text)
        if first_time:
            result.extractions.append(first_time)

        return result

    def _extract_citizenship(
        self,
        borrower_text: str,
        full_text: str,
    ) -> ExtractedValue:
        """Extract citizenship status using shared patterns."""
        # US Citizen - use shared compiled patterns
        for pattern in US_CITIZEN_PATTERNS_COMPILED:
            if pattern.search(full_text):
                return ExtractedValue(
                    field_name="citizenship_status",
                    value="US_CITIZEN",
                    confidence=ConfidenceScores.REGEX_HIGH,
                    source_text=sanitize_source_text(full_text[:200]),
                    extraction_method="regex",
                )

        # Permanent Resident
        for pattern in PERMANENT_RESIDENT_PATTERNS_COMPILED:
            if pattern.search(full_text):
                return ExtractedValue(
                    field_name="citizenship_status",
                    value="PERMANENT_RESIDENT",
                    confidence=ConfidenceScores.REGEX_HIGH,
                    source_text=sanitize_source_text(full_text[:200]),
                    extraction_method="regex",
                )

        # Non-Permanent Resident
        for pattern in NON_PERMANENT_RESIDENT_PATTERNS_COMPILED:
            if pattern.search(full_text):
                return ExtractedValue(
                    field_name="citizenship_status",
                    value="NON_PERMANENT_RESIDENT",
                    confidence=ConfidenceScores.REGEX_MEDIUM,
                    source_text=sanitize_source_text(full_text[:200]),
                    extraction_method="regex",
                )

        return None

    def _extract_bankruptcy(
        self,
        borrower_text: str,
        full_text: str,
    ) -> List[ExtractedValue]:
        """Extract bankruptcy information."""
        extractions = []

        # Check for bankruptcy mention
        bk_yes_patterns = [
            r"(?:filed|had|went through|declared)\s*bankruptcy",
            r"bankruptcy.*?(?:yes|filed|had)",
        ]

        bk_no_patterns = [
            r"(?:no|never|haven\'t)\s*(?:had|filed)?\s*bankruptcy",
            r"bankruptcy.*?(?:no|never|haven\'t)",
        ]

        has_bankruptcy = None

        for pattern in bk_no_patterns:
            if re.search(pattern, full_text, re.IGNORECASE):
                has_bankruptcy = False
                break

        if has_bankruptcy is None:
            for pattern in bk_yes_patterns:
                if re.search(pattern, full_text, re.IGNORECASE):
                    has_bankruptcy = True
                    break

        if has_bankruptcy is not None:
            extractions.append(ExtractedValue(
                field_name="has_bankruptcy",
                value=has_bankruptcy,
                confidence=ConfidenceScores.REGEX_HIGH,
                source_text=sanitize_source_text(full_text[:200]),
            ))

        # If yes, try to extract chapter and discharge date
        if has_bankruptcy:
            # Chapter
            chapter_pattern = r"chapter\s*(\d+)"
            match = re.search(chapter_pattern, full_text, re.IGNORECASE)
            if match:
                chapter = match.group(1)
                if chapter in ["7", "13", "11"]:
                    extractions.append(ExtractedValue(
                        field_name="bankruptcy_chapter",
                        value=f"Chapter {chapter}",
                        confidence=ConfidenceScores.REGEX_HIGH,
                        source_text=sanitize_source_text(full_text[max(0, match.start()-20):match.end()+20]),
                    ))

            # Discharge date
            date_extraction = self.extract_date(full_text, "bankruptcy_discharge_date")
            if date_extraction:
                extractions.append(date_extraction)

        return extractions

    def _extract_foreclosure(
        self,
        borrower_text: str,
        full_text: str,
    ) -> ExtractedValue:
        """Extract foreclosure information."""
        fc_no_patterns = [
            r"(?:no|never|haven\'t)\s*(?:had|been)?\s*(?:a\s+)?foreclosure",
            r"foreclosure.*?(?:no|never)",
        ]

        fc_yes_patterns = [
            r"(?:had|been through|went through)\s*(?:a\s+)?foreclosure",
            r"foreclosure.*?(?:yes|had)",
            r"lost.*?home.*?(?:bank|foreclosure)",
        ]

        for pattern in fc_no_patterns:
            if re.search(pattern, full_text, re.IGNORECASE):
                return ExtractedValue(
                    field_name="has_foreclosure",
                    value=False,
                    confidence=ConfidenceScores.REGEX_HIGH,
                    source_text=sanitize_source_text(full_text[:200]),
                )

        for pattern in fc_yes_patterns:
            if re.search(pattern, full_text, re.IGNORECASE):
                return ExtractedValue(
                    field_name="has_foreclosure",
                    value=True,
                    confidence=ConfidenceScores.REGEX_MEDIUM,
                    source_text=sanitize_source_text(full_text[:200]),
                )

        return None

    def _extract_judgments(
        self,
        borrower_text: str,
        full_text: str,
    ) -> ExtractedValue:
        """Extract judgment information."""
        jdg_no_patterns = [
            r"(?:no|never|don\'t have)\s*(?:any\s+)?(?:outstanding\s+)?judgment",
            r"judgment.*?(?:no|never|none)",
        ]

        jdg_yes_patterns = [
            r"(?:have|had)\s*(?:an?\s+)?(?:outstanding\s+)?judgment",
            r"judgment.*?(?:yes|have|against me)",
        ]

        for pattern in jdg_no_patterns:
            if re.search(pattern, full_text, re.IGNORECASE):
                return ExtractedValue(
                    field_name="has_outstanding_judgments",
                    value=False,
                    confidence=ConfidenceScores.REGEX_MEDIUM,
                    source_text=sanitize_source_text(full_text[:200]),
                )

        for pattern in jdg_yes_patterns:
            if re.search(pattern, full_text, re.IGNORECASE):
                return ExtractedValue(
                    field_name="has_outstanding_judgments",
                    value=True,
                    confidence=ConfidenceScores.REGEX_DEFAULT,
                    source_text=sanitize_source_text(full_text[:200]),
                )

        return None

    def _extract_occupancy(
        self,
        borrower_text: str,
        full_text: str,
    ) -> ExtractedValue:
        """Extract occupancy intent."""
        primary_patterns = [
            r"(?:live|living|move|moving)\s*(?:in|into|there)",
            r"(?:primary|main)\s*(?:residence|home)",
            r"(?:will|going to)\s*(?:live|reside)\s*(?:in|there)",
        ]

        investment_patterns = [
            r"(?:investment|rental)\s*(?:property|home)",
            r"(?:rent|renting)\s*(?:it\s+)?out",
            r"(?:won\'t|not)\s*(?:be\s+)?living\s*(?:in|there)",
        ]

        second_home_patterns = [
            r"(?:second|vacation)\s*(?:home|property|house)",
            r"(?:weekend|summer)\s*(?:home|house|place)",
        ]

        for pattern in primary_patterns:
            if re.search(pattern, full_text, re.IGNORECASE):
                return ExtractedValue(
                    field_name="will_occupy_as_primary",
                    value=True,
                    confidence=ConfidenceScores.REGEX_HIGH,
                    source_text=sanitize_source_text(full_text[:200]),
                )

        for pattern in investment_patterns:
            if re.search(pattern, full_text, re.IGNORECASE):
                return ExtractedValue(
                    field_name="will_occupy_as_primary",
                    value=False,
                    confidence=ConfidenceScores.REGEX_HIGH,
                    source_text=sanitize_source_text(full_text[:200]),
                )

        for pattern in second_home_patterns:
            if re.search(pattern, full_text, re.IGNORECASE):
                return ExtractedValue(
                    field_name="property_use",
                    value="SECOND_HOME",
                    confidence=ConfidenceScores.REGEX_MEDIUM,
                    source_text=sanitize_source_text(full_text[:200]),
                )

        return None

    def _extract_first_time_buyer(
        self,
        borrower_text: str,
        full_text: str,
    ) -> ExtractedValue:
        """Extract first-time homebuyer status."""
        ftb_yes_patterns = [
            r"first\s*(?:time|home)\s*(?:home)?buyer",
            r"never\s*(?:owned|bought)\s*(?:a\s+)?(?:home|house|property)",
            r"(?:this is|it\'s)\s*(?:my|our)\s*first\s*(?:home|house)",
        ]

        ftb_no_patterns = [
            r"(?:owned|bought)\s*(?:a\s+)?(?:home|house|property)\s*before",
            r"(?:currently|already)\s*own",
            r"(?:not|isn\'t)\s*(?:a\s+)?first\s*time",
        ]

        for pattern in ftb_yes_patterns:
            if re.search(pattern, full_text, re.IGNORECASE):
                return ExtractedValue(
                    field_name="first_time_buyer",
                    value=True,
                    confidence=ConfidenceScores.REGEX_HIGH,
                    source_text=sanitize_source_text(full_text[:200]),
                )

        for pattern in ftb_no_patterns:
            if re.search(pattern, full_text, re.IGNORECASE):
                return ExtractedValue(
                    field_name="first_time_buyer",
                    value=False,
                    confidence=ConfidenceScores.REGEX_HIGH,
                    source_text=sanitize_source_text(full_text[:200]),
                )

        return None
