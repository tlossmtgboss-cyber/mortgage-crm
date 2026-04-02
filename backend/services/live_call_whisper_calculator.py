"""
Live Call Whisper Calculator Service

Real-time calculator trigger detection and suggestion generation for live calls.
Detects when mortgage calculations would be helpful during a call and provides
pre-calculated results as whisper suggestions to loan officers.

Features:
- Pattern-based trigger detection (keywords, phrases)
- Context-aware calculator selection
- Pre-calculated results for instant display
- Integration with LiveCallWhisperService
"""

import re
import uuid
import logging
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass

from .calculator_service import calculator_service
from .live_call_whisper_service import (
    Whisper,
    WhisperType,
    WhisperPriority,
    CallContext,
)

logger = logging.getLogger(__name__)


# Calculator trigger patterns organized by calculator type
CALCULATOR_TRIGGERS = {
    "payment": {
        "patterns": [
            r"what would my payment",
            r"monthly payment",
            r"how much per month",
            r"what's the payment",
            r"payment.*be",
            r"afford.*month",
            r"monthly.*(cost|amount)",
        ],
        "calculator": "piti",
        "priority": WhisperPriority.HIGH,
    },
    "affordability": {
        "patterns": [
            r"how much can i afford",
            r"what can i qualify for",
            r"max(imum)? purchase price",
            r"qualify.*(for|with)",
            r"budget.*(is|around)",
            r"price range",
            r"what price",
        ],
        "calculator": "affordability",
        "priority": WhisperPriority.HIGH,
    },
    "pmi": {
        "patterns": [
            r"mortgage insurance",
            r"\bpmi\b",
            r"\bmip\b",
            r"need (pmi|insurance)",
            r"avoid (pmi|insurance)",
            r"20 percent down",
            r"less than 20",
            r"insurance.*(cost|monthly)",
        ],
        "calculator": "pmi",
        "priority": WhisperPriority.MEDIUM,
    },
    "dti": {
        "patterns": [
            r"debt to income",
            r"\bdti\b",
            r"qualify with.*(debt|income)",
            r"too much debt",
            r"ratio",
            r"debts.*(affect|impact)",
        ],
        "calculator": "dti",
        "priority": WhisperPriority.MEDIUM,
    },
    "comparison": {
        "patterns": [
            r"compare",
            r"difference between",
            r"15 year vs 30",
            r"fha vs conventional",
            r"which (is|would be) better",
            r"pros and cons",
        ],
        "calculator": "comparison",
        "priority": WhisperPriority.MEDIUM,
    },
    "down_payment": {
        "patterns": [
            r"down payment",
            r"percent down",
            r"how much.*(down|need)",
            r"minimum down",
            r"\bltv\b",
        ],
        "calculator": "ltv",
        "priority": WhisperPriority.MEDIUM,
    },
    "closing_costs": {
        "patterns": [
            r"closing costs",
            r"cash to close",
            r"bring to closing",
            r"total.*(cost|need)",
            r"out of pocket",
            r"fees",
        ],
        "calculator": "closing_costs",
        "priority": WhisperPriority.MEDIUM,
    },
}


@dataclass
class CalculatorContext:
    """Context for calculator suggestions extracted from call."""
    loan_amount: Optional[float] = None
    property_value: Optional[float] = None
    down_payment: Optional[float] = None
    down_payment_percent: Optional[float] = None
    interest_rate: Optional[float] = None
    term_years: int = 30
    loan_type: str = "conventional"
    credit_score: Optional[int] = None
    monthly_income: Optional[float] = None
    annual_income: Optional[float] = None
    monthly_debts: Optional[float] = None
    state: Optional[str] = None


class CalculatorWhisperDetector:
    """
    Detects calculator opportunities in live call transcripts
    and generates pre-calculated whisper suggestions.
    """

    def __init__(self):
        # Compile regex patterns for efficiency
        self.compiled_triggers = {}
        for trigger_type, config in CALCULATOR_TRIGGERS.items():
            self.compiled_triggers[trigger_type] = {
                "patterns": [re.compile(p, re.IGNORECASE) for p in config["patterns"]],
                "calculator": config["calculator"],
                "priority": config["priority"],
            }

        # Track recent suggestions to avoid duplicates
        self.recent_suggestions: Dict[str, datetime] = {}
        self.suggestion_cooldown_seconds = 60  # Don't repeat same suggestion within 60s

    def detect_calculator_opportunity(
        self,
        text: str,
        call_context: CallContext,
    ) -> Optional[Whisper]:
        """
        Detect if transcript contains a calculator opportunity.

        Args:
            text: Recent transcript text to analyze
            call_context: Current call context with loan/borrower info

        Returns:
            Whisper suggestion with pre-calculated result, or None
        """
        text_lower = text.lower()

        for trigger_type, config in self.compiled_triggers.items():
            for pattern in config["patterns"]:
                if pattern.search(text_lower):
                    # Check cooldown
                    cooldown_key = f"{call_context.call_id}_{trigger_type}"
                    if self._is_on_cooldown(cooldown_key):
                        continue

                    # Build calculator context from call context
                    calc_context = self._build_calculator_context(call_context, text)

                    # Try to run the calculation
                    result = self._run_calculation(
                        config["calculator"],
                        calc_context,
                        trigger_type,
                    )

                    if result:
                        whisper = self._create_whisper(
                            trigger_type,
                            config["calculator"],
                            result,
                            config["priority"],
                            text,
                        )

                        # Update cooldown
                        self.recent_suggestions[cooldown_key] = datetime.now(timezone.utc)

                        return whisper

        return None

    def _is_on_cooldown(self, key: str) -> bool:
        """Check if a suggestion type is on cooldown."""
        if key not in self.recent_suggestions:
            return False

        elapsed = (datetime.now(timezone.utc) - self.recent_suggestions[key]).total_seconds()
        return elapsed < self.suggestion_cooldown_seconds

    def _build_calculator_context(
        self,
        call_context: CallContext,
        text: str,
    ) -> CalculatorContext:
        """Build calculator context from call context and extract numbers from text."""
        calc_context = CalculatorContext(
            loan_amount=call_context.loan_amount,
            loan_type=call_context.loan_type or "conventional",
            credit_score=call_context.credit_score,
        )

        # Try to extract numbers from the text
        numbers = self._extract_numbers_from_text(text)

        # Update context with extracted values
        for value, context_hint in numbers:
            if "thousand" in context_hint or "k" in context_hint.lower():
                value = value * 1000

            if any(word in context_hint.lower() for word in ["price", "home", "house", "property", "value"]):
                calc_context.property_value = value
            elif any(word in context_hint.lower() for word in ["loan", "borrow", "finance"]):
                calc_context.loan_amount = value
            elif any(word in context_hint.lower() for word in ["down", "dp"]):
                if value <= 100:
                    calc_context.down_payment_percent = value
                else:
                    calc_context.down_payment = value
            elif any(word in context_hint.lower() for word in ["rate", "percent", "interest"]):
                if value < 20:  # Likely an interest rate
                    calc_context.interest_rate = value
            elif any(word in context_hint.lower() for word in ["income", "make", "earn", "salary"]):
                if value > 10000:
                    calc_context.annual_income = value
                else:
                    calc_context.monthly_income = value
            elif any(word in context_hint.lower() for word in ["debt", "payment", "owe"]):
                calc_context.monthly_debts = value
            elif any(word in context_hint.lower() for word in ["score", "credit"]):
                if 300 <= value <= 850:
                    calc_context.credit_score = int(value)

        # Calculate derived values
        if calc_context.property_value and calc_context.down_payment_percent:
            calc_context.down_payment = calc_context.property_value * (calc_context.down_payment_percent / 100)

        if calc_context.property_value and calc_context.down_payment:
            if not calc_context.loan_amount:
                calc_context.loan_amount = calc_context.property_value - calc_context.down_payment

        # Use defaults if needed
        if not calc_context.interest_rate:
            calc_context.interest_rate = 6.875  # Current typical rate

        return calc_context

    def _extract_numbers_from_text(self, text: str) -> List[Tuple[float, str]]:
        """Extract numbers with their surrounding context from text."""
        results = []

        # Pattern for currency amounts
        currency_pattern = r'\$?([\d,]+(?:\.\d{2})?)\s*(thousand|k|million|m)?'
        for match in re.finditer(currency_pattern, text, re.IGNORECASE):
            value = float(match.group(1).replace(",", ""))
            multiplier = match.group(2) or ""
            if multiplier.lower() in ["thousand", "k"]:
                value *= 1000
            elif multiplier.lower() in ["million", "m"]:
                value *= 1000000

            # Get surrounding context (20 chars before and after)
            start = max(0, match.start() - 20)
            end = min(len(text), match.end() + 20)
            context = text[start:end]
            results.append((value, context))

        # Pattern for percentages
        percent_pattern = r'([\d.]+)\s*(%|percent)'
        for match in re.finditer(percent_pattern, text, re.IGNORECASE):
            value = float(match.group(1))
            start = max(0, match.start() - 20)
            end = min(len(text), match.end() + 20)
            context = text[start:end]
            results.append((value, context))

        return results

    def _run_calculation(
        self,
        calculator_type: str,
        context: CalculatorContext,
        trigger_type: str,
    ) -> Optional[Dict[str, Any]]:
        """Run the appropriate calculation based on available data."""
        try:
            if calculator_type == "piti" or calculator_type == "payment":
                if context.loan_amount and context.interest_rate:
                    property_value = context.property_value or context.loan_amount * 1.25
                    return calculator_service.calculate_piti(
                        loan_amount=context.loan_amount,
                        interest_rate=context.interest_rate,
                        term_years=context.term_years,
                        property_value=property_value,
                        credit_score=context.credit_score or 720,
                        loan_type=context.loan_type,
                    )

            elif calculator_type == "affordability":
                income = context.annual_income or (context.monthly_income * 12 if context.monthly_income else None)
                if income and context.interest_rate:
                    return calculator_service.calculate_affordability(
                        annual_income=income,
                        monthly_debts=context.monthly_debts or 0,
                        down_payment=context.down_payment or 0,
                        interest_rate=context.interest_rate,
                    )

            elif calculator_type == "pmi":
                if context.loan_amount and context.property_value:
                    return calculator_service.calculate_pmi(
                        loan_amount=context.loan_amount,
                        home_value=context.property_value,
                        credit_score=context.credit_score or 720,
                        loan_type=context.loan_type,
                    )

            elif calculator_type == "dti":
                income = context.monthly_income or (context.annual_income / 12 if context.annual_income else None)
                if income and context.loan_amount and context.interest_rate:
                    piti = calculator_service.calculate_piti(
                        loan_amount=context.loan_amount,
                        interest_rate=context.interest_rate,
                        term_years=30,
                        property_value=context.property_value or context.loan_amount * 1.25,
                    )
                    return calculator_service.calculate_dti(
                        monthly_income=income,
                        monthly_debts=context.monthly_debts or 0,
                        proposed_housing_payment=piti["total_piti"],
                    )

            elif calculator_type == "ltv":
                if context.loan_amount and context.property_value:
                    return calculator_service.calculate_ltv(
                        loan_amount=context.loan_amount,
                        property_value=context.property_value,
                    )

            elif calculator_type == "closing_costs":
                if context.loan_amount and context.property_value:
                    return calculator_service.estimate_closing_costs(
                        loan_amount=context.loan_amount,
                        property_value=context.property_value,
                        state=context.state or "CA",
                        loan_type=context.loan_type,
                    )

            elif calculator_type == "comparison":
                # Run payment comparison for 15 vs 30 year
                if context.loan_amount and context.interest_rate:
                    result_30 = calculator_service.calculate_monthly_pi(
                        loan_amount=context.loan_amount,
                        interest_rate=context.interest_rate,
                        term_years=30,
                    )
                    result_15 = calculator_service.calculate_monthly_pi(
                        loan_amount=context.loan_amount,
                        interest_rate=context.interest_rate - 0.5,  # 15yr typically lower
                        term_years=15,
                    )
                    return {
                        "comparison": "term",
                        "30_year": result_30,
                        "15_year": result_15,
                        "monthly_difference": result_15["monthly_payment"] - result_30["monthly_payment"],
                        "interest_savings": result_30["total_interest"] - result_15["total_interest"],
                    }

        except Exception as e:
            logger.error(f"Calculator whisper error for {calculator_type}: {e}")

        return None

    def _create_whisper(
        self,
        trigger_type: str,
        calculator_type: str,
        result: Dict[str, Any],
        priority: WhisperPriority,
        trigger_text: str,
    ) -> Whisper:
        """Create a whisper from calculation result."""
        whisper_id = str(uuid.uuid4())[:8]

        # Generate title and content based on calculator type
        title, content = self._format_whisper_content(calculator_type, result)

        return Whisper(
            id=whisper_id,
            type=WhisperType.CALCULATOR_SUGGESTION,
            priority=priority,
            title=title,
            content=content,
            context=f"Triggered by: '{trigger_text[:50]}...' " if len(trigger_text) > 50 else f"Triggered by: '{trigger_text}'",
        )

    def _format_whisper_content(
        self,
        calculator_type: str,
        result: Dict[str, Any],
    ) -> Tuple[str, str]:
        """Format whisper title and content for display."""
        if calculator_type == "piti":
            title = f"💰 Payment: ${result['total_piti']:,.0f}/mo"
            content = (
                f"P&I: ${result['principal_interest']:,.0f}\n"
                f"Taxes: ${result['property_tax_monthly']:,.0f}\n"
                f"Insurance: ${result['insurance_monthly']:,.0f}\n"
                f"PMI: ${result['pmi_monthly']:,.0f}"
            )

        elif calculator_type == "affordability":
            title = f"🏠 Max Price: ${result['max_purchase_price']:,.0f}"
            content = (
                f"Max Loan: ${result['max_loan_amount']:,.0f}\n"
                f"Est. Payment: ${result['estimated_monthly_payment']:,.0f}/mo\n"
                f"Est. DTI: {result['estimated_dti']:.1f}%"
            )

        elif calculator_type == "pmi":
            if result.get("required"):
                title = f"🛡️ MI: ${result['monthly_premium']:,.0f}/mo"
                content = (
                    f"Type: {result['type']}\n"
                    f"LTV: {result['ltv']:.1f}%\n"
                    + (f"Upfront: ${result['upfront_premium']:,.0f}" if result.get('upfront_premium', 0) > 0 else "")
                )
            else:
                title = "✅ No MI Required"
                content = f"LTV: {result['ltv']:.1f}% (≤80%)"

        elif calculator_type == "dti":
            qualifies = result.get("qualifies", False)
            title = f"📊 DTI: {result['back_end_dti']:.1f}%"
            content = (
                f"Front-end: {result['front_end_dti']:.1f}%\n"
                f"Back-end: {result['back_end_dti']:.1f}%\n"
                f"Status: {'✅ Qualifies' if qualifies else '⚠️ Over 43%'}"
            )

        elif calculator_type == "ltv":
            title = f"📐 LTV: {result['ltv']:.1f}%"
            content = (
                f"Down Payment: ${result['down_payment']:,.0f}\n"
                f"({result['down_payment_percent']:.1f}%)\n"
                f"PMI: {'Required' if result['pmi_required'] else 'Not Required'}"
            )

        elif calculator_type == "closing_costs":
            title = f"💵 Closing: ${result['total_closing_costs']:,.0f}"
            content = (
                f"Lender Fees: ${result['lender_fees']['total']:,.0f}\n"
                f"Third Party: ${result['third_party_fees']['total']:,.0f}\n"
                f"Prepaids: ${result['prepaids']['total']:,.0f}"
            )

        elif calculator_type == "comparison":
            title = "📊 15yr vs 30yr Comparison"
            content = (
                f"30yr: ${result['30_year']['monthly_payment']:,.0f}/mo\n"
                f"15yr: ${result['15_year']['monthly_payment']:,.0f}/mo\n"
                f"Savings: ${result['interest_savings']:,.0f} total interest"
            )

        else:
            title = f"Calculator Result"
            content = str(result)

        return title, content


# Singleton instance for easy import
calculator_whisper_detector = CalculatorWhisperDetector()
