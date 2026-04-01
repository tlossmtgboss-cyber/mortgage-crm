"""
Financial Extraction Agent

Extracts income, asset, and liability information from call transcripts.
"""

import re
from typing import List, Dict, Any
import logging

from .base_agent import BaseExtractionAgent, ConfidenceScores, ValidationRanges
from ..data_contracts import (
    TranscriptSegment,
    ExtractionResult,
    ExtractedValue,
)
from ..pii_utils import sanitize_source_text

logger = logging.getLogger(__name__)


class FinancialExtractionAgent(BaseExtractionAgent):
    """Agent for extracting financial information."""

    AGENT_NAME = "financial"
    AGENT_VERSION = "2.0"  # LLM-first extraction
    EXTRACTION_SCHEMA_KEY = "financial"
    RECOMMENDED_MODEL = "sonnet"  # Complex financial reasoning (income calc, asset validation)

    def extract_with_regex(
        self,
        segments: List[TranscriptSegment],
        existing_data: Dict[str, Any] = None,
    ) -> ExtractionResult:
        """Fallback regex-based extraction for financial fields."""
        result = ExtractionResult(agent_name=self.AGENT_NAME)

        borrower_text = self.get_borrower_text(segments)
        full_text = self.get_full_text(segments)

        # Extract income
        income = self._extract_income(borrower_text, full_text)
        result.extractions.extend(income)

        # Extract assets
        assets = self._extract_assets(borrower_text, full_text)
        result.extractions.extend(assets)

        # Extract liabilities
        liabilities = self._extract_liabilities(borrower_text, full_text)
        result.extractions.extend(liabilities)

        # Extract down payment
        down_payment = self._extract_down_payment(full_text)
        if down_payment:
            result.extractions.extend(down_payment)

        return result

    def _extract_income(
        self,
        borrower_text: str,
        full_text: str,
    ) -> List[ExtractedValue]:
        """Extract income information."""
        extractions = []

        # Annual salary
        annual_patterns = [
            r"(?:make|earn|salary is|income is|gross)\s*\$?([\d,]+)\s*(?:a year|per year|annually|yearly)",
            r"\$?([\d,]+)\s*(?:a year|per year|annually)\s*(?:salary|income)?",
            r"(?:annual|yearly)\s*(?:salary|income)\s*(?:of|is)?\s*\$?([\d,]+)",
        ]

        for pattern in annual_patterns:
            match = re.search(pattern, full_text, re.IGNORECASE)
            if match:
                value_str = match.group(1).replace(',', '')
                try:
                    value = float(value_str)
                    if ValidationRanges.MIN_ANNUAL_SALARY <= value <= ValidationRanges.MAX_ANNUAL_SALARY:
                        extractions.append(ExtractedValue(
                            field_name="annual_salary",
                            value=value,
                            confidence=ConfidenceScores.REGEX_MEDIUM,
                            source_text=sanitize_source_text(full_text[max(0, match.start()-30):match.end()+30]),
                        ))
                        # Calculate monthly
                        extractions.append(ExtractedValue(
                            field_name="monthly_salary",
                            value=round(value / 12, 2),
                            confidence=ConfidenceScores.REGEX_MEDIUM,
                            source_text="Calculated from annual",
                        ))
                        break
                except ValueError:
                    continue

        # Monthly salary
        if not any(e.field_name == "monthly_salary" for e in extractions):
            monthly_patterns = [
                r"(?:make|earn|salary is|income is)\s*\$?([\d,]+)\s*(?:a month|per month|monthly)",
                r"\$?([\d,]+)\s*(?:a month|per month|monthly)\s*(?:salary|income)?",
            ]

            for pattern in monthly_patterns:
                match = re.search(pattern, full_text, re.IGNORECASE)
                if match:
                    value_str = match.group(1).replace(',', '')
                    try:
                        value = float(value_str)
                        if ValidationRanges.MIN_MONTHLY_SALARY <= value <= ValidationRanges.MAX_MONTHLY_SALARY:
                            extractions.append(ExtractedValue(
                                field_name="monthly_salary",
                                value=value,
                                confidence=ConfidenceScores.REGEX_MEDIUM,
                                source_text=sanitize_source_text(full_text[max(0, match.start()-30):match.end()+30]),
                            ))
                            break
                    except ValueError:
                        continue

        # Hourly wage
        hourly_patterns = [
            r"(?:make|earn|paid|get)\s*\$?([\d.]+)\s*(?:an hour|per hour|hourly)",
            r"\$?([\d.]+)\s*(?:an hour|per hour|hourly)",
        ]

        for pattern in hourly_patterns:
            match = re.search(pattern, full_text, re.IGNORECASE)
            if match:
                value_str = match.group(1).replace(',', '')
                try:
                    value = float(value_str)
                    if ValidationRanges.MIN_HOURLY_RATE <= value <= ValidationRanges.MAX_HOURLY_RATE:
                        extractions.append(ExtractedValue(
                            field_name="hourly_rate",
                            value=value,
                            confidence=ConfidenceScores.REGEX_MEDIUM,
                            source_text=sanitize_source_text(full_text[max(0, match.start()-30):match.end()+30]),
                        ))
                        break
                except ValueError:
                    continue

        # Variable income (bonus, commission, overtime)
        variable_types = [
            ("bonus", r"(?:bonus|bonuses).*?\$?([\d,]+)"),
            ("commission", r"(?:commission|commissions).*?\$?([\d,]+)"),
            ("overtime", r"(?:overtime|ot).*?\$?([\d,]+)"),
        ]

        for income_type, pattern in variable_types:
            match = re.search(pattern, full_text, re.IGNORECASE)
            if match:
                value_str = match.group(1).replace(',', '')
                try:
                    value = float(value_str)
                    if value > 0:
                        extractions.append(ExtractedValue(
                            field_name=income_type,
                            value=value,
                            confidence=ConfidenceScores.REGEX_LOW,
                            source_text=sanitize_source_text(full_text[max(0, match.start()-30):match.end()+30]),
                        ))
                except ValueError:
                    continue

        return extractions

    def _extract_assets(
        self,
        borrower_text: str,
        full_text: str,
    ) -> List[ExtractedValue]:
        """Extract asset information."""
        extractions = []

        # Bank accounts / savings
        savings_patterns = [
            r"(?:savings?|checking|bank|account).*?\$?([\d,]+)",
            r"\$?([\d,]+)\s*(?:in (?:the )?bank|saved|in savings)",
        ]

        for pattern in savings_patterns:
            match = re.search(pattern, full_text, re.IGNORECASE)
            if match:
                value_str = match.group(1).replace(',', '')
                try:
                    value = float(value_str)
                    if value >= ValidationRanges.MIN_ASSET_BALANCE:
                        extractions.append(ExtractedValue(
                            field_name="bank_balance",
                            value=value,
                            confidence=ConfidenceScores.REGEX_LOW,
                            source_text=sanitize_source_text(full_text[max(0, match.start()-30):match.end()+30]),
                        ))
                        break
                except ValueError:
                    continue

        # Retirement accounts
        retirement_patterns = [
            r"(?:401k|401\(k\)|retirement|ira).*?\$?([\d,]+)",
            r"\$?([\d,]+)\s*(?:in (?:my )?(?:401k|retirement|ira))",
        ]

        for pattern in retirement_patterns:
            match = re.search(pattern, full_text, re.IGNORECASE)
            if match:
                value_str = match.group(1).replace(',', '')
                try:
                    value = float(value_str)
                    if value >= ValidationRanges.MIN_ASSET_BALANCE:
                        extractions.append(ExtractedValue(
                            field_name="retirement_balance",
                            value=value,
                            confidence=ConfidenceScores.REGEX_LOW,
                            source_text=sanitize_source_text(full_text[max(0, match.start()-30):match.end()+30]),
                        ))
                        break
                except ValueError:
                    continue

        # Gift funds
        gift_patterns = [
            r"(?:gift|gifting|gifted).*?\$?([\d,]+)",
            r"\$?([\d,]+)\s*(?:gift|as a gift)",
        ]

        for pattern in gift_patterns:
            match = re.search(pattern, full_text, re.IGNORECASE)
            if match:
                value_str = match.group(1).replace(',', '')
                try:
                    value = float(value_str)
                    if value >= ValidationRanges.MIN_ASSET_BALANCE:
                        extractions.append(ExtractedValue(
                            field_name="gift_amount",
                            value=value,
                            confidence=ConfidenceScores.REGEX_DEFAULT,
                            source_text=sanitize_source_text(full_text[max(0, match.start()-30):match.end()+30]),
                        ))
                        break
                except ValueError:
                    continue

        return extractions

    def _extract_liabilities(
        self,
        borrower_text: str,
        full_text: str,
    ) -> List[ExtractedValue]:
        """Extract liability information."""
        extractions = []

        # Car payment
        car_patterns = [
            r"(?:car|auto|vehicle)\s*(?:payment|loan).*?\$?([\d,]+)",
            r"\$?([\d,]+)\s*(?:for (?:my )?car|car payment)",
        ]

        for pattern in car_patterns:
            match = re.search(pattern, full_text, re.IGNORECASE)
            if match:
                value_str = match.group(1).replace(',', '')
                try:
                    value = float(value_str)
                    if ValidationRanges.MIN_CAR_PAYMENT <= value <= ValidationRanges.MAX_CAR_PAYMENT:
                        extractions.append(ExtractedValue(
                            field_name="car_payment",
                            value=value,
                            confidence=ConfidenceScores.REGEX_DEFAULT,
                            source_text=sanitize_source_text(full_text[max(0, match.start()-30):match.end()+30]),
                        ))
                        break
                except ValueError:
                    continue

        # Student loans
        student_patterns = [
            r"(?:student|school)\s*loan.*?\$?([\d,]+)",
            r"\$?([\d,]+)\s*(?:for student|student loan)",
        ]

        for pattern in student_patterns:
            match = re.search(pattern, full_text, re.IGNORECASE)
            if match:
                value_str = match.group(1).replace(',', '')
                try:
                    value = float(value_str)
                    if value > 0:
                        extractions.append(ExtractedValue(
                            field_name="student_loan_payment",
                            value=value,
                            confidence=ConfidenceScores.REGEX_DEFAULT,
                            source_text=sanitize_source_text(full_text[max(0, match.start()-30):match.end()+30]),
                        ))
                        break
                except ValueError:
                    continue

        # Credit card payments
        cc_patterns = [
            r"(?:credit card|cc).*?(?:payment|pay).*?\$?([\d,]+)",
            r"\$?([\d,]+)\s*(?:on credit cards|credit card payment)",
        ]

        for pattern in cc_patterns:
            match = re.search(pattern, full_text, re.IGNORECASE)
            if match:
                value_str = match.group(1).replace(',', '')
                try:
                    value = float(value_str)
                    if value > 0:
                        extractions.append(ExtractedValue(
                            field_name="credit_card_payments",
                            value=value,
                            confidence=ConfidenceScores.REGEX_LOW,
                            source_text=sanitize_source_text(full_text[max(0, match.start()-30):match.end()+30]),
                        ))
                        break
                except ValueError:
                    continue

        return extractions

    def _extract_down_payment(self, full_text: str) -> List[ExtractedValue]:
        """Extract down payment information."""
        extractions = []

        # Down payment amount
        dp_patterns = [
            r"(?:down payment|putting down).*?\$?([\d,]+)",
            r"\$?([\d,]+)\s*(?:down|for (?:a )?down payment)",
        ]

        for pattern in dp_patterns:
            match = re.search(pattern, full_text, re.IGNORECASE)
            if match:
                value_str = match.group(1).replace(',', '')
                try:
                    value = float(value_str)
                    if value >= ValidationRanges.MIN_DOWN_PAYMENT:
                        extractions.append(ExtractedValue(
                            field_name="down_payment_amount",
                            value=value,
                            confidence=ConfidenceScores.REGEX_MEDIUM,
                            source_text=sanitize_source_text(full_text[max(0, match.start()-30):match.end()+30]),
                        ))
                        break
                except ValueError:
                    continue

        # Down payment percentage
        pct_pattern = r"(\d+)%?\s*(?:down|down payment)"
        match = re.search(pct_pattern, full_text, re.IGNORECASE)
        if match:
            try:
                pct = int(match.group(1))
                if ValidationRanges.MIN_DOWN_PAYMENT_PERCENT <= pct <= ValidationRanges.MAX_DOWN_PAYMENT_PERCENT:
                    extractions.append(ExtractedValue(
                        field_name="down_payment_percentage",
                        value=pct,
                        confidence=ConfidenceScores.REGEX_MEDIUM,
                        source_text=sanitize_source_text(full_text[max(0, match.start()-30):match.end()+30]),
                    ))
            except ValueError:
                pass

        # Down payment source
        sources = [
            ("savings", r"(?:down payment|putting down).*?(?:from )?(?:my )?savings"),
            ("gift", r"(?:down payment|putting down).*?(?:gift|gifted)"),
            ("401k", r"(?:down payment|putting down).*?(?:401k|retirement)"),
            ("sale_of_home", r"(?:down payment|putting down).*?(?:selling|sale of|sold).*?home"),
        ]

        for source, pattern in sources:
            if re.search(pattern, full_text, re.IGNORECASE):
                extractions.append(ExtractedValue(
                    field_name="down_payment_source",
                    value=source,
                    confidence=ConfidenceScores.REGEX_DEFAULT,
                    source_text=sanitize_source_text(full_text[:200]),
                ))
                break

        return extractions
