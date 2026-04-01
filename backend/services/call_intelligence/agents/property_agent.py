"""
Property Extraction Agent

Extracts property and address information from call transcripts.
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


class PropertyExtractionAgent(BaseExtractionAgent):
    """Agent for extracting property/address information."""

    AGENT_NAME = "property"
    AGENT_VERSION = "2.0"  # LLM-first extraction
    EXTRACTION_SCHEMA_KEY = "property"
    RECOMMENDED_MODEL = "haiku"  # Address/property type extraction is straightforward

    # US States
    STATES = {
        "alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR",
        "california": "CA", "colorado": "CO", "connecticut": "CT", "delaware": "DE",
        "florida": "FL", "georgia": "GA", "hawaii": "HI", "idaho": "ID",
        "illinois": "IL", "indiana": "IN", "iowa": "IA", "kansas": "KS",
        "kentucky": "KY", "louisiana": "LA", "maine": "ME", "maryland": "MD",
        "massachusetts": "MA", "michigan": "MI", "minnesota": "MN", "mississippi": "MS",
        "missouri": "MO", "montana": "MT", "nebraska": "NE", "nevada": "NV",
        "new hampshire": "NH", "new jersey": "NJ", "new mexico": "NM", "new york": "NY",
        "north carolina": "NC", "north dakota": "ND", "ohio": "OH", "oklahoma": "OK",
        "oregon": "OR", "pennsylvania": "PA", "rhode island": "RI", "south carolina": "SC",
        "south dakota": "SD", "tennessee": "TN", "texas": "TX", "utah": "UT",
        "vermont": "VT", "virginia": "VA", "washington": "WA", "west virginia": "WV",
        "wisconsin": "WI", "wyoming": "WY"
    }

    def extract_with_regex(
        self,
        segments: List[TranscriptSegment],
        existing_data: Dict[str, Any] = None,
    ) -> ExtractionResult:
        """Fallback regex-based extraction for property fields."""
        result = ExtractionResult(agent_name=self.AGENT_NAME)

        borrower_text = self.get_borrower_text(segments)
        full_text = self.get_full_text(segments)

        # Extract current address
        address = self._extract_address(borrower_text, full_text)
        if address:
            result.extractions.extend(address)

        # Extract housing status
        housing = self._extract_housing_status(borrower_text, full_text)
        if housing:
            result.extractions.append(housing)

        # Extract monthly payment
        payment = self._extract_housing_payment(borrower_text, full_text)
        if payment:
            result.extractions.append(payment)

        # Extract duration at address
        duration = self._extract_duration(borrower_text, full_text)
        if duration:
            result.extractions.extend(duration)

        # Extract property type (for subject property)
        prop_type = self._extract_property_type(full_text)
        if prop_type:
            result.extractions.append(prop_type)

        # Extract purchase price
        price = self._extract_purchase_price(full_text)
        if price:
            result.extractions.append(price)

        return result

    def _extract_address(
        self,
        borrower_text: str,
        full_text: str,
    ) -> List[ExtractedValue]:
        """Extract address components."""
        extractions = []

        # Street address pattern
        street_pattern = r"(\d+\s+(?:[A-Za-z]+\s+){1,4}(?:Street|St|Avenue|Ave|Road|Rd|Drive|Dr|Lane|Ln|Court|Ct|Boulevard|Blvd|Way|Place|Pl)\.?)"
        match = re.search(street_pattern, full_text, re.IGNORECASE)
        if match:
            extractions.append(ExtractedValue(
                field_name="street",
                value=match.group(1).strip(),
                confidence=ConfidenceScores.REGEX_MEDIUM,
                source_text=sanitize_source_text(full_text[max(0, match.start()-20):match.end()+50]),
            ))

        # City pattern (after street or "in [City]")
        city_pattern = r"(?:in|city of|live in|living in)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)"
        match = re.search(city_pattern, full_text)
        if match:
            city = match.group(1).strip()
            # Verify it's not a state name
            if city.lower() not in self.STATES:
                extractions.append(ExtractedValue(
                    field_name="city",
                    value=city,
                    confidence=ConfidenceScores.REGEX_DEFAULT,
                    source_text=sanitize_source_text(full_text[max(0, match.start()-20):match.end()+30]),
                ))

        # State pattern
        for state_name, abbrev in self.STATES.items():
            if re.search(rf"\b{state_name}\b", full_text, re.IGNORECASE) or \
               re.search(rf"\b{abbrev}\b", full_text):
                extractions.append(ExtractedValue(
                    field_name="state",
                    value=abbrev,
                    confidence=ConfidenceScores.REGEX_HIGH,
                    source_text=f"Found: {state_name.title()}",
                ))
                break

        # ZIP code pattern
        zip_pattern = r"\b(\d{5}(?:-\d{4})?)\b"
        match = re.search(zip_pattern, full_text)
        if match:
            extractions.append(ExtractedValue(
                field_name="zip",
                value=match.group(1),
                confidence=ConfidenceScores.REGEX_HIGH,
                source_text=sanitize_source_text(full_text[max(0, match.start()-30):match.end()+30]),
            ))

        return extractions

    def _extract_housing_status(
        self,
        borrower_text: str,
        full_text: str,
    ) -> ExtractedValue:
        """Extract own/rent status."""
        own_patterns = [
            r"\b(?:i own|we own|own my|own our|homeowner|own the house|own the home)\b",
            r"\b(?:my house|my home|our house|our home)\b",
        ]

        rent_patterns = [
            r"\b(?:i rent|we rent|renting|tenant|lease|landlord)\b",
            r"\b(?:rent is|pay rent|monthly rent)\b",
        ]

        free_patterns = [
            r"\b(?:rent free|live with parents|living with family|no rent)\b",
        ]

        for pattern in own_patterns:
            if re.search(pattern, full_text, re.IGNORECASE):
                return ExtractedValue(
                    field_name="ownership_status",
                    value="OWN",
                    confidence=ConfidenceScores.REGEX_HIGH,
                    source_text=sanitize_source_text(full_text[:200]),
                )

        for pattern in rent_patterns:
            if re.search(pattern, full_text, re.IGNORECASE):
                return ExtractedValue(
                    field_name="ownership_status",
                    value="RENT",
                    confidence=ConfidenceScores.REGEX_HIGH,
                    source_text=sanitize_source_text(full_text[:200]),
                )

        for pattern in free_patterns:
            if re.search(pattern, full_text, re.IGNORECASE):
                return ExtractedValue(
                    field_name="ownership_status",
                    value="LIVING_RENT_FREE",
                    confidence=ConfidenceScores.REGEX_MEDIUM,
                    source_text=sanitize_source_text(full_text[:200]),
                )

        return None

    def _extract_housing_payment(
        self,
        borrower_text: str,
        full_text: str,
    ) -> ExtractedValue:
        """Extract monthly housing payment."""
        patterns = [
            r"(?:rent|mortgage|payment|paying).*?\$?([\d,]+)",
            r"\$?([\d,]+).*?(?:per month|a month|monthly|rent|mortgage)",
        ]

        for pattern in patterns:
            match = re.search(pattern, full_text, re.IGNORECASE)
            if match:
                amount = match.group(1).replace(',', '')
                try:
                    value = float(amount)
                    # Sanity check - reasonable housing payment
                    if 100 <= value <= 20000:
                        return ExtractedValue(
                            field_name="monthly_payment",
                            value=value,
                            confidence=ConfidenceScores.REGEX_DEFAULT,
                            source_text=sanitize_source_text(full_text[max(0, match.start()-30):match.end()+30]),
                        )
                except ValueError:
                    continue

        return None

    def _extract_duration(
        self,
        borrower_text: str,
        full_text: str,
    ) -> List[ExtractedValue]:
        """Extract time at current address."""
        extractions = []

        # Years pattern
        year_pattern = r"(\d+)\s*years?(?:\s+(?:at|in|here|there|living))?"
        match = re.search(year_pattern, full_text, re.IGNORECASE)
        if match:
            years = int(match.group(1))
            if years <= 50:  # Sanity check
                extractions.append(ExtractedValue(
                    field_name="years_at_address",
                    value=years,
                    confidence=ConfidenceScores.REGEX_MEDIUM,
                    source_text=sanitize_source_text(full_text[max(0, match.start()-30):match.end()+30]),
                ))

        # Months pattern
        month_pattern = r"(\d+)\s*months?(?:\s+(?:at|in|here|there|living))?"
        match = re.search(month_pattern, full_text, re.IGNORECASE)
        if match:
            months = int(match.group(1))
            if months <= 11:
                extractions.append(ExtractedValue(
                    field_name="months_at_address",
                    value=months,
                    confidence=ConfidenceScores.REGEX_DEFAULT,
                    source_text=sanitize_source_text(full_text[max(0, match.start()-30):match.end()+30]),
                ))

        return extractions

    def _extract_property_type(self, full_text: str) -> ExtractedValue:
        """Extract property type."""
        type_map = {
            "SFR": [r"\b(?:single family|single-family|sfr|house|home)\b"],
            "CONDO": [r"\b(?:condo|condominium)\b"],
            "TOWNHOUSE": [r"\b(?:townhouse|townhome|town house)\b"],
            "MULTI_UNIT": [r"\b(?:duplex|triplex|fourplex|multi-?family|multi-?unit)\b"],
        }

        for prop_type, patterns in type_map.items():
            for pattern in patterns:
                if re.search(pattern, full_text, re.IGNORECASE):
                    return ExtractedValue(
                        field_name="property_type",
                        value=prop_type,
                        confidence=ConfidenceScores.REGEX_MEDIUM,
                        source_text=sanitize_source_text(full_text[:200]),
                    )

        return None

    def _extract_purchase_price(self, full_text: str) -> ExtractedValue:
        """Extract purchase price."""
        patterns = [
            r"(?:purchase price|buying for|offer|asking price).*?\$?([\d,]+(?:k|K|000)?)",
            r"\$?([\d,]+(?:k|K|000)?).*?(?:purchase|buying|offer)",
        ]

        for pattern in patterns:
            match = re.search(pattern, full_text, re.IGNORECASE)
            if match:
                value_str = match.group(1).replace(',', '').upper()

                try:
                    if 'K' in value_str:
                        value = float(value_str.replace('K', '')) * 1000
                    else:
                        value = float(value_str)

                    # Sanity check for home prices
                    if 50000 <= value <= 10_000_000:
                        return ExtractedValue(
                            field_name="purchase_price",
                            value=value,
                            confidence=ConfidenceScores.REGEX_DEFAULT,
                            source_text=sanitize_source_text(full_text[max(0, match.start()-30):match.end()+30]),
                        )
                except ValueError:
                    continue

        return None
