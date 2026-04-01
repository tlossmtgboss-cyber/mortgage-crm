"""
Intent Extraction Agent

Extracts loan intent and preferences from call transcripts.
"""

import re
from typing import List, Dict, Any
import logging

from .base_agent import BaseExtractionAgent, ConfidenceScores
from ..data_contracts import (
    TranscriptSegment,
    ExtractionResult,
    ExtractedValue,
)
from ..pii_utils import sanitize_source_text

logger = logging.getLogger(__name__)


class IntentExtractionAgent(BaseExtractionAgent):
    """Agent for extracting loan intent and preferences."""

    AGENT_NAME = "intent"
    AGENT_VERSION = "2.0"  # LLM-first extraction
    EXTRACTION_SCHEMA_KEY = "intent"
    RECOMMENDED_MODEL = "haiku"  # Intent/preference extraction is structured

    def extract_with_regex(
        self,
        segments: List[TranscriptSegment],
        existing_data: Dict[str, Any] = None,
    ) -> ExtractionResult:
        """Fallback regex-based extraction for intent fields."""
        result = ExtractionResult(agent_name=self.AGENT_NAME)

        borrower_text = self.get_borrower_text(segments)
        full_text = self.get_full_text(segments)

        # Extract loan purpose
        purpose = self._extract_loan_purpose(full_text)
        if purpose:
            result.extractions.append(purpose)

        # Extract timeline
        timeline = self._extract_timeline(full_text)
        if timeline:
            result.extractions.extend(timeline)

        # Extract loan type preference
        loan_type = self._extract_loan_type(full_text)
        if loan_type:
            result.extractions.append(loan_type)

        # Extract rate preference
        rate_pref = self._extract_rate_preference(full_text)
        if rate_pref:
            result.extractions.append(rate_pref)

        # Extract pre-approval status
        preapproval = self._extract_preapproval(full_text)
        if preapproval:
            result.extractions.append(preapproval)

        # Extract realtor info
        realtor = self._extract_realtor_info(full_text)
        if realtor:
            result.extractions.extend(realtor)

        return result

    def _extract_loan_purpose(self, full_text: str) -> ExtractedValue:
        """Extract loan purpose."""
        purpose_map = {
            "PURCHASE": [
                r"\b(?:buy|buying|purchase|purchasing)\s+(?:a\s+)?(?:home|house|property)\b",
                r"\b(?:looking for|want|need)\s+(?:a\s+)?(?:new\s+)?home\b",
                r"\b(?:first\s+home|new\s+house|looking\s+to\s+buy)\b",
            ],
            "REFINANCE": [
                r"\b(?:refinance|refi|refinancing)\b",
                r"\b(?:lower\s+(?:my\s+)?rate|reduce\s+(?:my\s+)?payment)\b",
                r"\b(?:get\s+a\s+better\s+rate)\b",
            ],
            "CASH_OUT": [
                r"\b(?:cash\s+out|pull\s+(?:out\s+)?equity|access\s+(?:my\s+)?equity)\b",
                r"\b(?:take\s+(?:out\s+)?cash|get\s+cash\s+(?:out|from))\b",
            ],
            "CONSTRUCTION": [
                r"\b(?:build|building|construction)\s+(?:a\s+)?(?:new\s+)?(?:home|house)\b",
                r"\b(?:new\s+construction)\b",
            ],
        }

        for purpose, patterns in purpose_map.items():
            for pattern in patterns:
                if re.search(pattern, full_text, re.IGNORECASE):
                    return ExtractedValue(
                        field_name="loan_purpose",
                        value=purpose,
                        confidence=ConfidenceScores.REGEX_HIGH,
                        source_text=sanitize_source_text(full_text[:200]),
                    )

        return None

    def _extract_timeline(self, full_text: str) -> List[ExtractedValue]:
        """Extract timeline/urgency."""
        extractions = []

        # Specific timeframes
        timeline_patterns = [
            (r"(?:next|within)\s*(\d+)\s*(?:days?|weeks?)", "days/weeks"),
            (r"(?:next|within)\s*(\d+)\s*months?", "months"),
            (r"(?:in|by)\s*(january|february|march|april|may|june|july|august|september|october|november|december)", "month_name"),
            (r"(?:end\s+of|by\s+the\s+end\s+of)\s*(january|february|march|april|may|june|july|august|september|october|november|december)", "month_name"),
        ]

        for pattern, timeframe_type in timeline_patterns:
            match = re.search(pattern, full_text, re.IGNORECASE)
            if match:
                value = match.group(1)
                extractions.append(ExtractedValue(
                    field_name="target_timeline",
                    value=value,
                    confidence=ConfidenceScores.REGEX_DEFAULT,
                    source_text=sanitize_source_text(full_text[max(0, match.start()-30):match.end()+30]),
                ))
                break

        # Urgency level
        urgency_patterns = {
            "URGENT": [
                r"\b(?:asap|right away|immediately|urgent|quick|fast)\b",
                r"\b(?:need|have) to (?:close|move|buy) (?:quickly|soon|fast)\b",
            ],
            "SOON": [
                r"\b(?:soon|next few weeks|next month)\b",
                r"\b(?:looking to (?:close|move) soon)\b",
            ],
            "EXPLORING": [
                r"\b(?:just looking|exploring|shopping around|researching)\b",
                r"\b(?:not in a hurry|no rush|take (?:our|my) time)\b",
            ],
        }

        for urgency, patterns in urgency_patterns.items():
            for pattern in patterns:
                if re.search(pattern, full_text, re.IGNORECASE):
                    extractions.append(ExtractedValue(
                        field_name="urgency",
                        value=urgency,
                        confidence=ConfidenceScores.REGEX_DEFAULT,
                        source_text=sanitize_source_text(full_text[:200]),
                    ))
                    break

        return extractions

    def _extract_loan_type(self, full_text: str) -> ExtractedValue:
        """Extract loan type preference."""
        type_map = {
            "CONVENTIONAL": [r"\b(?:conventional|conforming)\b"],
            "FHA": [r"\b(?:fha)\b"],
            "VA": [r"\b(?:va|veteran)\s*(?:loan)?\b"],
            "USDA": [r"\b(?:usda|rural)\s*(?:loan)?\b"],
            "JUMBO": [r"\b(?:jumbo)\b"],
        }

        for loan_type, patterns in type_map.items():
            for pattern in patterns:
                if re.search(pattern, full_text, re.IGNORECASE):
                    return ExtractedValue(
                        field_name="loan_type_preference",
                        value=loan_type,
                        confidence=ConfidenceScores.REGEX_MEDIUM,
                        source_text=sanitize_source_text(full_text[:200]),
                    )

        return None

    def _extract_rate_preference(self, full_text: str) -> ExtractedValue:
        """Extract rate type preference."""
        fixed_patterns = [
            r"\b(?:fixed\s+rate|fixed)\b",
            r"\b(?:want|prefer)\s+(?:a\s+)?fixed\b",
        ]

        arm_patterns = [
            r"\b(?:arm|adjustable|variable)\b",
            r"\b(?:5/1|7/1|10/1)\s*(?:arm)?\b",
        ]

        for pattern in fixed_patterns:
            if re.search(pattern, full_text, re.IGNORECASE):
                return ExtractedValue(
                    field_name="rate_type_preference",
                    value="FIXED",
                    confidence=ConfidenceScores.REGEX_HIGH,
                    source_text=sanitize_source_text(full_text[:200]),
                )

        for pattern in arm_patterns:
            if re.search(pattern, full_text, re.IGNORECASE):
                return ExtractedValue(
                    field_name="rate_type_preference",
                    value="ARM",
                    confidence=ConfidenceScores.REGEX_MEDIUM,
                    source_text=sanitize_source_text(full_text[:200]),
                )

        return None

    def _extract_preapproval(self, full_text: str) -> ExtractedValue:
        """Extract pre-approval status."""
        has_preapproval = [
            r"\b(?:already|have\s+a)\s*(?:pre-?approved|pre-?approval)\b",
            r"\b(?:got|received)\s*(?:pre-?approved|pre-?approval)\b",
        ]

        needs_preapproval = [
            r"\b(?:need|want|get)\s*(?:pre-?approved|pre-?approval)\b",
            r"\b(?:looking for|seeking)\s*(?:pre-?approval)\b",
            r"\b(?:not yet|don\'t have)\s*(?:pre-?approved|pre-?approval)\b",
        ]

        for pattern in has_preapproval:
            if re.search(pattern, full_text, re.IGNORECASE):
                return ExtractedValue(
                    field_name="has_preapproval",
                    value=True,
                    confidence=ConfidenceScores.REGEX_HIGH,
                    source_text=sanitize_source_text(full_text[:200]),
                )

        for pattern in needs_preapproval:
            if re.search(pattern, full_text, re.IGNORECASE):
                return ExtractedValue(
                    field_name="has_preapproval",
                    value=False,
                    confidence=ConfidenceScores.REGEX_MEDIUM,
                    source_text=sanitize_source_text(full_text[:200]),
                )

        return None

    def _extract_realtor_info(self, full_text: str) -> List[ExtractedValue]:
        """Extract realtor/agent information."""
        extractions = []

        has_realtor_patterns = [
            r"\b(?:have|working with|using)\s*(?:a\s+)?(?:realtor|real estate agent|agent)\b",
            r"\b(?:my|our)\s+(?:realtor|agent)\b",
        ]

        no_realtor_patterns = [
            r"\b(?:don\'t have|no|looking for)\s*(?:a\s+)?(?:realtor|agent)\b",
        ]

        for pattern in has_realtor_patterns:
            if re.search(pattern, full_text, re.IGNORECASE):
                extractions.append(ExtractedValue(
                    field_name="has_realtor",
                    value=True,
                    confidence=ConfidenceScores.REGEX_HIGH,
                    source_text=sanitize_source_text(full_text[:200]),
                ))

                # Try to extract realtor name
                name_pattern = r"(?:realtor|agent)(?:\'s name)?\s+(?:is\s+)?([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)"
                match = re.search(name_pattern, full_text, re.IGNORECASE)
                if match:
                    extractions.append(ExtractedValue(
                        field_name="realtor_name",
                        value=match.group(1).strip(),
                        confidence=ConfidenceScores.REGEX_LOW,
                        source_text=sanitize_source_text(full_text[max(0, match.start()-20):match.end()+30]),
                    ))
                break

        for pattern in no_realtor_patterns:
            if re.search(pattern, full_text, re.IGNORECASE):
                extractions.append(ExtractedValue(
                    field_name="has_realtor",
                    value=False,
                    confidence=ConfidenceScores.REGEX_MEDIUM,
                    source_text=sanitize_source_text(full_text[:200]),
                ))
                break

        return extractions
