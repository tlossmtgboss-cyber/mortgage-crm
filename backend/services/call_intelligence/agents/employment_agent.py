"""
Employment Extraction Agent

Extracts employment information from call transcripts.
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


class EmploymentExtractionAgent(BaseExtractionAgent):
    """Agent for extracting employment information."""

    AGENT_NAME = "employment"
    AGENT_VERSION = "2.0"  # LLM-first extraction
    EXTRACTION_SCHEMA_KEY = "employment"
    RECOMMENDED_MODEL = "haiku"  # Simple structured data extraction (employer, title, income)

    def extract_with_regex(
        self,
        segments: List[TranscriptSegment],
        existing_data: Dict[str, Any] = None,
    ) -> ExtractionResult:
        """Fallback regex-based extraction for employment fields."""
        result = ExtractionResult(agent_name=self.AGENT_NAME)

        borrower_text = self.get_borrower_text(segments)
        full_text = self.get_full_text(segments)

        # Extract employer name
        employer = self._extract_employer(borrower_text, full_text)
        if employer:
            result.extractions.append(employer)

        # Extract job title
        title = self._extract_job_title(borrower_text, full_text)
        if title:
            result.extractions.append(title)

        # Extract employment type
        emp_type = self._extract_employment_type(borrower_text, full_text)
        if emp_type:
            result.extractions.append(emp_type)

        # Extract self-employment
        self_emp = self._extract_self_employment(borrower_text, full_text)
        if self_emp:
            result.extractions.extend(self_emp)

        # Extract duration
        duration = self._extract_duration(borrower_text, full_text)
        if duration:
            result.extractions.extend(duration)

        # Extract employer phone
        emp_phone = self._extract_employer_phone(full_text)
        if emp_phone:
            result.extractions.append(emp_phone)

        return result

    def _extract_employer(
        self,
        borrower_text: str,
        full_text: str,
    ) -> ExtractedValue:
        """Extract employer name."""
        patterns = [
            r"(?:work(?:ing)? (?:at|for)|employed (?:at|by|with)|job (?:at|with))\s+([A-Z][A-Za-z\s&]+?)(?:\.|,|$|\s+(?:as|for|in|since))",
            r"(?:employer|company|work)\s+(?:is|called|named)\s+([A-Z][A-Za-z\s&]+?)(?:\.|,|$)",
            r"([A-Z][A-Za-z\s&]+?)\s+(?:is my employer|employs me|hired me)",
        ]

        for pattern in patterns:
            match = re.search(pattern, full_text, re.IGNORECASE)
            if match:
                employer = match.group(1).strip()
                # Clean up
                employer = re.sub(r'\s+', ' ', employer)
                if len(employer) > 2:
                    return ExtractedValue(
                        field_name="employer",
                        value=employer,
                        confidence=ConfidenceScores.REGEX_MEDIUM,
                        source_text=sanitize_source_text(full_text[max(0, match.start()-20):match.end()+20]),
                    )

        return None

    def _extract_job_title(
        self,
        borrower_text: str,
        full_text: str,
    ) -> ExtractedValue:
        """Extract job title/position."""
        patterns = [
            r"(?:i'm|i am|work as|position is|title is|job is)\s+(?:a |an )?([A-Za-z\s]+?)(?:\.|,|$|\s+(?:at|for|with))",
            r"(?:my (?:job|position|title|role) is)\s+(?:a |an )?([A-Za-z\s]+?)(?:\.|,|$)",
        ]

        # Common job titles to look for
        common_titles = [
            "manager", "director", "engineer", "developer", "analyst",
            "nurse", "teacher", "sales", "consultant", "accountant",
            "technician", "supervisor", "coordinator", "specialist",
            "assistant", "administrator", "officer", "executive"
        ]

        for pattern in patterns:
            match = re.search(pattern, full_text, re.IGNORECASE)
            if match:
                title = match.group(1).strip()
                # Validate it looks like a job title
                title_lower = title.lower()
                if any(t in title_lower for t in common_titles) or len(title.split()) <= 4:
                    return ExtractedValue(
                        field_name="position",
                        value=title.title(),
                        confidence=ConfidenceScores.REGEX_DEFAULT,
                        source_text=sanitize_source_text(full_text[max(0, match.start()-20):match.end()+20]),
                    )

        return None

    def _extract_employment_type(
        self,
        borrower_text: str,
        full_text: str,
    ) -> ExtractedValue:
        """Extract employment type (full-time, part-time, etc.)."""
        type_map = {
            "FULL_TIME": [r"\b(?:full[- ]?time|salaried)\b"],
            "PART_TIME": [r"\b(?:part[- ]?time)\b"],
            "CONTRACT": [r"\b(?:contract|contractor|1099)\b"],
            "SEASONAL": [r"\b(?:seasonal)\b"],
        }

        for emp_type, patterns in type_map.items():
            for pattern in patterns:
                if re.search(pattern, full_text, re.IGNORECASE):
                    return ExtractedValue(
                        field_name="employment_type",
                        value=emp_type,
                        confidence=ConfidenceScores.REGEX_MEDIUM,
                        source_text=sanitize_source_text(full_text[:200]),
                    )

        return None

    def _extract_self_employment(
        self,
        borrower_text: str,
        full_text: str,
    ) -> List[ExtractedValue]:
        """Extract self-employment details."""
        extractions = []

        self_emp_patterns = [
            r"\b(?:self[- ]?employed|own(?:er)? (?:of|my)|my (?:own )?business|entrepreneur)\b",
            r"\b(?:run (?:a |my )?business|freelance|independent contractor)\b",
        ]

        for pattern in self_emp_patterns:
            if re.search(pattern, full_text, re.IGNORECASE):
                extractions.append(ExtractedValue(
                    field_name="is_self_employed",
                    value=True,
                    confidence=ConfidenceScores.REGEX_HIGH,
                    source_text=sanitize_source_text(full_text[:200]),
                ))

                # Try to extract business name
                biz_patterns = [
                    r"(?:business|company) (?:is called|named|is)\s+([A-Z][A-Za-z\s&]+?)(?:\.|,|$)",
                    r"(?:own|run)\s+([A-Z][A-Za-z\s&]+?)(?:\.|,|$)",
                ]

                for biz_pattern in biz_patterns:
                    match = re.search(biz_pattern, full_text, re.IGNORECASE)
                    if match:
                        extractions.append(ExtractedValue(
                            field_name="business_name",
                            value=match.group(1).strip(),
                            confidence=ConfidenceScores.REGEX_DEFAULT,
                            source_text=sanitize_source_text(full_text[max(0, match.start()-20):match.end()+20]),
                        ))
                        break

                # Try to extract ownership percentage
                ownership_pattern = r"(\d+)%?\s*(?:owner|ownership)"
                match = re.search(ownership_pattern, full_text, re.IGNORECASE)
                if match:
                    extractions.append(ExtractedValue(
                        field_name="ownership_percentage",
                        value=int(match.group(1)),
                        confidence=ConfidenceScores.REGEX_MEDIUM,
                        source_text=sanitize_source_text(full_text[max(0, match.start()-20):match.end()+20]),
                    ))

                break

        return extractions

    def _extract_duration(
        self,
        borrower_text: str,
        full_text: str,
    ) -> List[ExtractedValue]:
        """Extract employment duration."""
        extractions = []

        # Years at employer
        patterns = [
            r"(?:work(?:ed|ing)?|been there|employed|with them)\s+(?:for\s+)?(\d+)\s*years?",
            r"(\d+)\s*years?\s+(?:at|with|for)\s+(?:my job|the company|them|this company)",
            r"since\s+(\d{4})",
        ]

        for pattern in patterns:
            match = re.search(pattern, full_text, re.IGNORECASE)
            if match:
                value = match.group(1)
                if len(value) == 4:  # Year
                    from datetime import datetime
                    years = datetime.now().year - int(value)
                    extractions.append(ExtractedValue(
                        field_name="years_employed",
                        value=years,
                        confidence=ConfidenceScores.REGEX_DEFAULT,
                        source_text=sanitize_source_text(full_text[max(0, match.start()-20):match.end()+20]),
                    ))
                else:
                    extractions.append(ExtractedValue(
                        field_name="years_employed",
                        value=int(value),
                        confidence=ConfidenceScores.REGEX_MEDIUM,
                        source_text=sanitize_source_text(full_text[max(0, match.start()-20):match.end()+20]),
                    ))
                break

        # Months
        month_pattern = r"(\d+)\s*months?\s+(?:at|with|for|working)"
        match = re.search(month_pattern, full_text, re.IGNORECASE)
        if match:
            extractions.append(ExtractedValue(
                field_name="months_employed",
                value=int(match.group(1)),
                confidence=ConfidenceScores.REGEX_DEFAULT,
                source_text=sanitize_source_text(full_text[max(0, match.start()-20):match.end()+20]),
            ))

        return extractions

    def _extract_employer_phone(self, full_text: str) -> ExtractedValue:
        """Extract employer phone number."""
        # Look for phone after employer context
        patterns = [
            r"(?:employer|work|office|hr).*?(?:phone|number|call).*?(\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4})",
        ]

        for pattern in patterns:
            match = re.search(pattern, full_text, re.IGNORECASE)
            if match:
                phone = re.sub(r'[^\d]', '', match.group(1))
                if len(phone) == 10:
                    return ExtractedValue(
                        field_name="employer_phone",
                        value=phone,
                        confidence=ConfidenceScores.REGEX_DEFAULT,
                        source_text=sanitize_source_text(full_text[max(0, match.start()-20):match.end()+30]),
                    )

        return None
