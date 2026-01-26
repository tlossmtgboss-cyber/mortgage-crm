"""
Mortgage Calculator Service

Comprehensive calculator service for mortgage calculations including:
- Monthly P&I payments
- Full PITI calculations
- PMI/MIP/VA/USDA mortgage insurance
- DTI (Debt-to-Income) calculations
- LTV (Loan-to-Value) calculations
- Affordability analysis
- Closing cost estimates
- Amortization schedules

Formulas ported from frontend/src/lib/propertyTax/calculator.js and
frontend/src/lib/mortgageInsurance/calculator.js for consistency.
"""

import math
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from enum import Enum


class LoanType(str, Enum):
    CONVENTIONAL = "conventional"
    FHA = "fha"
    VA = "va"
    USDA = "usda"


class CreditTier(str, Enum):
    EXCELLENT = "excellent"      # 760+
    VERY_GOOD = "veryGood"       # 740-759
    GOOD = "good"                # 720-739
    ABOVE_AVERAGE = "aboveAverage"  # 700-719
    AVERAGE = "average"          # 680-699
    BELOW_AVERAGE = "belowAverage"  # 660-679
    FAIR = "fair"                # 640-659
    MINIMUM = "minimum"          # 620-639
    SUB_MINIMUM = "subMinimum"   # Below 620


# PMI Rate Tables (annual rates as decimals)
# From frontend/src/lib/mortgageInsurance/rateData.js
CONVENTIONAL_PMI_RATES = {
    CreditTier.EXCELLENT: {
        "95.01-97": 0.0098,
        "90.01-95": 0.0078,
        "85.01-90": 0.0052,
        "80.01-85": 0.0032,
    },
    CreditTier.VERY_GOOD: {
        "95.01-97": 0.0105,
        "90.01-95": 0.0085,
        "85.01-90": 0.0058,
        "80.01-85": 0.0038,
    },
    CreditTier.GOOD: {
        "95.01-97": 0.0118,
        "90.01-95": 0.0095,
        "85.01-90": 0.0065,
        "80.01-85": 0.0044,
    },
    CreditTier.ABOVE_AVERAGE: {
        "95.01-97": 0.0135,
        "90.01-95": 0.0108,
        "85.01-90": 0.0078,
        "80.01-85": 0.0052,
    },
    CreditTier.AVERAGE: {
        "95.01-97": 0.0155,
        "90.01-95": 0.0125,
        "85.01-90": 0.0095,
        "80.01-85": 0.0065,
    },
    CreditTier.BELOW_AVERAGE: {
        "95.01-97": 0.0185,
        "90.01-95": 0.0150,
        "85.01-90": 0.0115,
        "80.01-85": 0.0082,
    },
    CreditTier.FAIR: {
        "95.01-97": 0.0210,
        "90.01-95": 0.0175,
        "85.01-90": 0.0135,
        "80.01-85": 0.0098,
    },
    CreditTier.MINIMUM: {
        "95.01-97": 0.0235,
        "90.01-95": 0.0195,
        "85.01-90": 0.0155,
        "80.01-85": 0.0115,
    },
}

# FHA MIP Rates
FHA_MIP_RATES = {
    "upfront": 0.0175,  # 1.75%
    "annual": {
        "standard": {
            "90_and_under": {"rate": 0.0050, "duration": 11, "for_life": False},
            "over_90": {"rate": 0.0055, "duration": None, "for_life": True},
        },
        "short_term": {  # <= 15 years and <= $726,200
            "90_and_under": {"rate": 0.0015, "duration": 11, "for_life": False},
            "over_90": {"rate": 0.0040, "duration": None, "for_life": True},
        },
    },
}

# VA Funding Fee Rates
VA_FUNDING_FEE_RATES = {
    "first_use": {
        "no_down": 0.0215,
        "5_to_10_down": 0.0150,
        "10_plus_down": 0.0125,
    },
    "subsequent_use": {
        "no_down": 0.0330,
        "5_to_10_down": 0.0150,
        "10_plus_down": 0.0125,
    },
}

# USDA Guarantee Fee Rates
USDA_GUARANTEE_RATES = {
    "upfront": 0.01,   # 1.0%
    "annual": 0.0035,  # 0.35%
}

# State average closing cost percentages (as % of home price)
STATE_CLOSING_COSTS = {
    "AL": 0.025, "AK": 0.030, "AZ": 0.028, "AR": 0.025, "CA": 0.025,
    "CO": 0.028, "CT": 0.035, "DE": 0.035, "FL": 0.030, "GA": 0.028,
    "HI": 0.035, "ID": 0.030, "IL": 0.032, "IN": 0.028, "IA": 0.028,
    "KS": 0.028, "KY": 0.028, "LA": 0.030, "ME": 0.030, "MD": 0.035,
    "MA": 0.035, "MI": 0.032, "MN": 0.030, "MS": 0.025, "MO": 0.028,
    "MT": 0.030, "NE": 0.028, "NV": 0.030, "NH": 0.032, "NJ": 0.035,
    "NM": 0.028, "NY": 0.040, "NC": 0.028, "ND": 0.028, "OH": 0.030,
    "OK": 0.028, "OR": 0.030, "PA": 0.035, "RI": 0.032, "SC": 0.028,
    "SD": 0.028, "TN": 0.028, "TX": 0.032, "UT": 0.028, "VT": 0.030,
    "VA": 0.030, "WA": 0.030, "WV": 0.028, "WI": 0.030, "WY": 0.028,
    "DC": 0.040,
}

# Default effective property tax rate (national average ~1.07%)
DEFAULT_TAX_RATE = 0.0107


def get_credit_tier(credit_score: int) -> CreditTier:
    """Get credit tier based on credit score."""
    if credit_score >= 760:
        return CreditTier.EXCELLENT
    elif credit_score >= 740:
        return CreditTier.VERY_GOOD
    elif credit_score >= 720:
        return CreditTier.GOOD
    elif credit_score >= 700:
        return CreditTier.ABOVE_AVERAGE
    elif credit_score >= 680:
        return CreditTier.AVERAGE
    elif credit_score >= 660:
        return CreditTier.BELOW_AVERAGE
    elif credit_score >= 640:
        return CreditTier.FAIR
    elif credit_score >= 620:
        return CreditTier.MINIMUM
    else:
        return CreditTier.SUB_MINIMUM


def get_ltv_range_key(ltv: float) -> Optional[str]:
    """Get LTV range key for rate lookup. LTV as decimal (e.g., 0.95)."""
    ltv_percent = ltv * 100
    if ltv_percent > 95:
        return "95.01-97"
    elif ltv_percent > 90:
        return "90.01-95"
    elif ltv_percent > 85:
        return "85.01-90"
    elif ltv_percent > 80:
        return "80.01-85"
    return None  # No PMI needed


class MortgageCalculatorService:
    """
    Comprehensive mortgage calculator service.
    All calculations match the frontend implementations for consistency.
    """

    def calculate_monthly_pi(
        self,
        loan_amount: float,
        interest_rate: float,
        term_years: int = 30,
    ) -> Dict[str, Any]:
        """
        Calculate monthly principal and interest payment.

        Formula: M = P * [r(1+r)^n] / [(1+r)^n - 1]
        Where: P = loan amount, r = monthly rate, n = total payments

        Args:
            loan_amount: Loan amount in dollars
            interest_rate: Annual interest rate as percentage (e.g., 6.5 for 6.5%)
            term_years: Loan term in years

        Returns:
            Dict with monthly_payment, total_interest, total_cost
        """
        if loan_amount <= 0:
            return {
                "monthly_payment": 0,
                "total_interest": 0,
                "total_cost": 0,
                "error": "Loan amount must be positive",
            }

        # Convert annual rate percentage to monthly decimal
        monthly_rate = (interest_rate / 100) / 12
        num_payments = term_years * 12

        if monthly_rate == 0:
            monthly_payment = loan_amount / num_payments
        else:
            monthly_payment = (
                loan_amount * monthly_rate * math.pow(1 + monthly_rate, num_payments)
            ) / (math.pow(1 + monthly_rate, num_payments) - 1)

        total_cost = monthly_payment * num_payments
        total_interest = total_cost - loan_amount

        return {
            "monthly_payment": round(monthly_payment, 2),
            "total_interest": round(total_interest, 2),
            "total_cost": round(total_cost, 2),
            "inputs": {
                "loan_amount": loan_amount,
                "interest_rate": interest_rate,
                "term_years": term_years,
            },
        }

    def calculate_pmi(
        self,
        loan_amount: float,
        home_value: float,
        credit_score: int = 720,
        loan_type: str = "conventional",
        term_years: int = 30,
        is_first_va_use: bool = True,
        is_va_exempt: bool = False,
    ) -> Dict[str, Any]:
        """
        Calculate mortgage insurance for any loan type.

        Args:
            loan_amount: Loan amount in dollars
            home_value: Property value in dollars
            credit_score: Borrower's credit score
            loan_type: "conventional", "fha", "va", or "usda"
            term_years: Loan term in years
            is_first_va_use: Whether this is first VA loan use
            is_va_exempt: Whether borrower is VA funding fee exempt

        Returns:
            Dict with monthly_premium, annual_premium, upfront_premium, ltv, etc.
        """
        if home_value <= 0:
            return {"error": "Home value must be positive"}

        ltv = loan_amount / home_value
        down_payment_percent = ((home_value - loan_amount) / home_value) * 100

        loan_type_lower = loan_type.lower()

        if loan_type_lower == "fha":
            return self._calculate_fha_mip(loan_amount, home_value, ltv, term_years)
        elif loan_type_lower == "va":
            return self._calculate_va_funding_fee(
                loan_amount, home_value, ltv, down_payment_percent,
                is_first_va_use, is_va_exempt
            )
        elif loan_type_lower == "usda":
            return self._calculate_usda_fee(loan_amount, home_value, ltv)
        else:  # conventional
            return self._calculate_conventional_pmi(
                loan_amount, home_value, ltv, credit_score, term_years
            )

    def _calculate_conventional_pmi(
        self,
        loan_amount: float,
        home_value: float,
        ltv: float,
        credit_score: int,
        term_years: int,
    ) -> Dict[str, Any]:
        """Calculate conventional PMI."""
        # No PMI needed at 80% LTV or below
        if ltv <= 0.80:
            return {
                "required": False,
                "type": "none",
                "monthly_premium": 0,
                "annual_premium": 0,
                "upfront_premium": 0,
                "annual_rate": 0,
                "ltv": round(ltv * 100, 2),
                "notes": "No PMI required with 20% or more down payment.",
            }

        tier = get_credit_tier(credit_score)
        ltv_key = get_ltv_range_key(ltv)

        if not ltv_key:
            return {
                "required": False,
                "type": "none",
                "monthly_premium": 0,
                "annual_premium": 0,
                "upfront_premium": 0,
                "annual_rate": 0,
                "ltv": round(ltv * 100, 2),
            }

        # Get rate from table
        tier_rates = CONVENTIONAL_PMI_RATES.get(tier)
        if not tier_rates:
            # Use minimum tier with penalty for sub-minimum credit
            tier_rates = CONVENTIONAL_PMI_RATES[CreditTier.MINIMUM]
            annual_rate = tier_rates.get(ltv_key, 0.02) * 1.1
        else:
            annual_rate = tier_rates.get(ltv_key, 0.01)

        annual_premium = loan_amount * annual_rate
        monthly_premium = annual_premium / 12

        # Estimate months to PMI cancellation
        estimated_months = self._estimate_pmi_cancellation_months(
            loan_amount, home_value, ltv, term_years
        )

        return {
            "required": True,
            "type": "PMI",
            "monthly_premium": round(monthly_premium, 2),
            "annual_premium": round(annual_premium, 2),
            "upfront_premium": 0,
            "annual_rate": round(annual_rate * 100, 3),  # As percentage
            "ltv": round(ltv * 100, 2),
            "credit_tier": tier.value,
            "cancellation": {
                "can_cancel": True,
                "automatic_ltv": 78,
                "request_ltv": 80,
                "estimated_months": estimated_months,
            },
            "notes": f"PMI required until 78% LTV (automatic) or 80% LTV (by request). "
                     f"Estimated {estimated_months} months until automatic cancellation.",
        }

    def _calculate_fha_mip(
        self,
        loan_amount: float,
        home_value: float,
        ltv: float,
        term_years: int,
    ) -> Dict[str, Any]:
        """Calculate FHA MIP."""
        is_short_term = term_years <= 15 and loan_amount <= 726200
        ltv_category = "90_and_under" if ltv <= 0.90 else "over_90"

        rate_key = "short_term" if is_short_term else "standard"
        annual_data = FHA_MIP_RATES["annual"][rate_key][ltv_category]

        upfront_premium = round(loan_amount * FHA_MIP_RATES["upfront"], 2)
        annual_premium = round(loan_amount * annual_data["rate"], 2)
        monthly_premium = round(annual_premium / 12, 2)

        return {
            "required": True,
            "type": "FHA MIP",
            "monthly_premium": monthly_premium,
            "annual_premium": annual_premium,
            "upfront_premium": upfront_premium,
            "upfront_rate": FHA_MIP_RATES["upfront"] * 100,
            "annual_rate": annual_data["rate"] * 100,
            "ltv": round(ltv * 100, 2),
            "for_life_of_loan": annual_data["for_life"],
            "duration_years": annual_data["duration"],
            "cancellation": {
                "can_cancel": not annual_data["for_life"],
                "method": "automatic" if not annual_data["for_life"] else "refinance_only",
            },
            "notes": (
                f"Upfront MIP of {FHA_MIP_RATES['upfront'] * 100:.2f}% can be financed. "
                + ("MIP required for life of loan (LTV > 90%)." if annual_data["for_life"]
                   else f"MIP cancels after {annual_data['duration']} years.")
            ),
        }

    def _calculate_va_funding_fee(
        self,
        loan_amount: float,
        home_value: float,
        ltv: float,
        down_payment_percent: float,
        is_first_use: bool,
        is_exempt: bool,
    ) -> Dict[str, Any]:
        """Calculate VA Funding Fee."""
        if is_exempt:
            return {
                "required": False,
                "type": "VA Funding Fee",
                "monthly_premium": 0,
                "annual_premium": 0,
                "upfront_premium": 0,
                "upfront_rate": 0,
                "ltv": round(ltv * 100, 2),
                "notes": "Exempt from VA Funding Fee due to disability or other qualifying exemption.",
            }

        use_type = "first_use" if is_first_use else "subsequent_use"

        if down_payment_percent >= 10:
            fee_rate = VA_FUNDING_FEE_RATES[use_type]["10_plus_down"]
        elif down_payment_percent >= 5:
            fee_rate = VA_FUNDING_FEE_RATES[use_type]["5_to_10_down"]
        else:
            fee_rate = VA_FUNDING_FEE_RATES[use_type]["no_down"]

        upfront_premium = round(loan_amount * fee_rate, 2)

        return {
            "required": True,
            "type": "VA Funding Fee",
            "monthly_premium": 0,  # VA has no monthly MI
            "annual_premium": 0,
            "upfront_premium": upfront_premium,
            "upfront_rate": fee_rate * 100,
            "ltv": round(ltv * 100, 2),
            "is_first_use": is_first_use,
            "cancellation": {
                "can_cancel": False,
                "method": "not_applicable",
            },
            "notes": f"VA loans have no monthly MI. One-time funding fee of {fee_rate * 100:.2f}% can be financed.",
        }

    def _calculate_usda_fee(
        self,
        loan_amount: float,
        home_value: float,
        ltv: float,
    ) -> Dict[str, Any]:
        """Calculate USDA Guarantee Fee."""
        upfront_premium = round(loan_amount * USDA_GUARANTEE_RATES["upfront"], 2)
        annual_premium = round(loan_amount * USDA_GUARANTEE_RATES["annual"], 2)
        monthly_premium = round(annual_premium / 12, 2)

        return {
            "required": True,
            "type": "USDA Guarantee Fee",
            "monthly_premium": monthly_premium,
            "annual_premium": annual_premium,
            "upfront_premium": upfront_premium,
            "upfront_rate": USDA_GUARANTEE_RATES["upfront"] * 100,
            "annual_rate": USDA_GUARANTEE_RATES["annual"] * 100,
            "ltv": round(ltv * 100, 2),
            "cancellation": {
                "can_cancel": False,
                "method": "refinance_only",
            },
            "notes": "USDA annual fee is required for life of loan. Consider refinancing to conventional once you have 20% equity.",
        }

    def _estimate_pmi_cancellation_months(
        self,
        loan_amount: float,
        home_value: float,
        ltv: float,
        term_years: int,
        interest_rate: float = 7.0,
    ) -> int:
        """Estimate months until PMI can be automatically cancelled (78% LTV)."""
        if ltv <= 0.78:
            return 0

        target_ltv = 0.78
        target_balance = home_value * target_ltv
        monthly_rate = (interest_rate / 100) / 12
        total_payments = term_years * 12

        # Calculate monthly payment
        if monthly_rate == 0:
            monthly_payment = loan_amount / total_payments
        else:
            monthly_payment = (
                loan_amount * monthly_rate * math.pow(1 + monthly_rate, total_payments)
            ) / (math.pow(1 + monthly_rate, total_payments) - 1)

        # Simulate amortization
        balance = loan_amount
        months = 0

        while balance > target_balance and months < total_payments:
            interest_payment = balance * monthly_rate
            principal_payment = monthly_payment - interest_payment
            balance -= principal_payment
            months += 1

        return months

    def calculate_piti(
        self,
        loan_amount: float,
        interest_rate: float,
        term_years: int,
        property_value: float,
        annual_taxes: Optional[float] = None,
        annual_insurance: Optional[float] = None,
        hoa_monthly: float = 0,
        credit_score: int = 720,
        loan_type: str = "conventional",
        state_code: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Calculate full PITI payment (Principal, Interest, Taxes, Insurance).

        Args:
            loan_amount: Loan amount in dollars
            interest_rate: Annual interest rate as percentage
            term_years: Loan term in years
            property_value: Property value for PMI calculation
            annual_taxes: Annual property taxes (estimated if not provided)
            annual_insurance: Annual insurance (estimated if not provided)
            hoa_monthly: Monthly HOA fees
            credit_score: Borrower's credit score
            loan_type: Loan type for MI calculation
            state_code: Two-letter state code for tax/cost estimates

        Returns:
            Dict with complete PITI breakdown
        """
        # Calculate P&I
        pi_result = self.calculate_monthly_pi(loan_amount, interest_rate, term_years)
        principal_interest = pi_result["monthly_payment"]

        # Estimate taxes if not provided
        if annual_taxes is None:
            tax_rate = DEFAULT_TAX_RATE
            annual_taxes = property_value * tax_rate
        monthly_taxes = annual_taxes / 12

        # Estimate insurance if not provided (roughly 0.35% of home value)
        if annual_insurance is None:
            annual_insurance = property_value * 0.0035
        monthly_insurance = annual_insurance / 12

        # Calculate PMI/MIP
        pmi_result = self.calculate_pmi(
            loan_amount, property_value, credit_score, loan_type, term_years
        )
        monthly_pmi = pmi_result.get("monthly_premium", 0)

        # Total PITI
        total_piti = principal_interest + monthly_taxes + monthly_insurance + hoa_monthly + monthly_pmi

        # Calculate LTV
        ltv = (loan_amount / property_value) * 100

        return {
            "principal_interest": round(principal_interest, 2),
            "property_tax_monthly": round(monthly_taxes, 2),
            "insurance_monthly": round(monthly_insurance, 2),
            "pmi_monthly": round(monthly_pmi, 2),
            "hoa_monthly": round(hoa_monthly, 2),
            "total_piti": round(total_piti, 2),
            "ltv": round(ltv, 2),
            "inputs": {
                "loan_amount": loan_amount,
                "interest_rate": interest_rate,
                "term_years": term_years,
                "property_value": property_value,
                "annual_taxes": round(annual_taxes, 2),
                "annual_insurance": round(annual_insurance, 2),
                "hoa_monthly": hoa_monthly,
                "credit_score": credit_score,
                "loan_type": loan_type,
            },
            "pmi_details": pmi_result,
        }

    def calculate_dti(
        self,
        monthly_income: float,
        monthly_debts: float,
        proposed_housing_payment: float,
    ) -> Dict[str, Any]:
        """
        Calculate Debt-to-Income ratios.

        Args:
            monthly_income: Gross monthly income
            monthly_debts: Total monthly debt payments (excluding housing)
            proposed_housing_payment: Proposed total housing payment (PITI)

        Returns:
            Dict with front-end DTI, back-end DTI, and qualification status
        """
        if monthly_income <= 0:
            return {"error": "Monthly income must be positive"}

        # Front-end DTI (housing expense ratio)
        front_end_dti = (proposed_housing_payment / monthly_income) * 100

        # Back-end DTI (total debt ratio)
        total_monthly_debt = monthly_debts + proposed_housing_payment
        back_end_dti = (total_monthly_debt / monthly_income) * 100

        # Standard qualification thresholds
        front_end_limit = 28
        back_end_limit = 43  # QM limit

        qualifies_front = front_end_dti <= front_end_limit
        qualifies_back = back_end_dti <= back_end_limit

        return {
            "front_end_dti": round(front_end_dti, 2),
            "back_end_dti": round(back_end_dti, 2),
            "front_end_limit": front_end_limit,
            "back_end_limit": back_end_limit,
            "qualifies_front_end": qualifies_front,
            "qualifies_back_end": qualifies_back,
            "qualifies": qualifies_front and qualifies_back,
            "inputs": {
                "monthly_income": monthly_income,
                "monthly_debts": monthly_debts,
                "proposed_housing_payment": proposed_housing_payment,
            },
            "notes": self._generate_dti_notes(front_end_dti, back_end_dti),
        }

    def _generate_dti_notes(self, front_end: float, back_end: float) -> str:
        """Generate helpful notes about DTI."""
        notes = []

        if back_end > 50:
            notes.append("DTI above 50% - may require manual underwriting or non-QM loan.")
        elif back_end > 43:
            notes.append("DTI above 43% - may require compensating factors for QM qualification.")
        elif back_end > 36:
            notes.append("DTI in acceptable range but consider reducing debt for better rates.")
        else:
            notes.append("DTI is within excellent range for most loan programs.")

        if front_end > 31:
            notes.append("Housing ratio above 31% - some lenders may require additional documentation.")

        return " ".join(notes)

    def calculate_ltv(
        self,
        loan_amount: float,
        property_value: float,
    ) -> Dict[str, Any]:
        """
        Calculate Loan-to-Value ratio.

        Args:
            loan_amount: Loan amount in dollars
            property_value: Property value in dollars

        Returns:
            Dict with LTV, tier classification, and PMI requirement
        """
        if property_value <= 0:
            return {"error": "Property value must be positive"}

        ltv = (loan_amount / property_value) * 100
        down_payment = property_value - loan_amount
        down_payment_percent = (down_payment / property_value) * 100

        # Classify LTV tier
        if ltv <= 80:
            tier = "excellent"
            pmi_required = False
        elif ltv <= 90:
            tier = "good"
            pmi_required = True
        elif ltv <= 95:
            tier = "acceptable"
            pmi_required = True
        else:
            tier = "high"
            pmi_required = True

        return {
            "ltv": round(ltv, 2),
            "down_payment": round(down_payment, 2),
            "down_payment_percent": round(down_payment_percent, 2),
            "tier": tier,
            "pmi_required": pmi_required,
            "inputs": {
                "loan_amount": loan_amount,
                "property_value": property_value,
            },
            "notes": f"{'No PMI required.' if not pmi_required else 'PMI required until 80% LTV.'}",
        }

    def calculate_affordability(
        self,
        annual_income: float,
        monthly_debts: float,
        down_payment: float,
        interest_rate: float,
        max_dti: float = 0.43,
        term_years: int = 30,
        annual_tax_rate: float = 0.0107,
        annual_insurance_rate: float = 0.0035,
    ) -> Dict[str, Any]:
        """
        Calculate maximum affordable purchase price based on income.

        Args:
            annual_income: Gross annual income
            monthly_debts: Total monthly debt payments
            down_payment: Available down payment
            interest_rate: Expected interest rate (percentage)
            max_dti: Maximum back-end DTI ratio (default 43%)
            term_years: Loan term in years
            annual_tax_rate: Annual property tax rate (decimal)
            annual_insurance_rate: Annual insurance rate (decimal)

        Returns:
            Dict with max purchase price, max loan amount, estimated payment
        """
        monthly_income = annual_income / 12

        # Calculate max housing payment based on DTI
        max_total_debt = monthly_income * max_dti
        max_housing_payment = max_total_debt - monthly_debts

        if max_housing_payment <= 0:
            return {
                "error": "Existing debts exceed DTI limit",
                "max_purchase_price": 0,
                "max_loan_amount": 0,
            }

        # Estimate tax and insurance portion
        # We need to solve for property value where payment = P&I + tax + insurance
        # This is iterative since tax/insurance depend on property value

        # Start with rough estimate
        monthly_rate = (interest_rate / 100) / 12
        num_payments = term_years * 12

        # Solve iteratively
        for _ in range(10):  # Converges quickly
            # Assume some loan amount
            estimated_home_value = max_housing_payment * 300  # Rough multiplier

            # Calculate tax and insurance based on this value
            monthly_tax = (estimated_home_value * annual_tax_rate) / 12
            monthly_insurance = (estimated_home_value * annual_insurance_rate) / 12

            # Remaining for P&I
            available_for_pi = max_housing_payment - monthly_tax - monthly_insurance

            if available_for_pi <= 0:
                break

            # Calculate max loan from P&I payment
            if monthly_rate == 0:
                max_loan = available_for_pi * num_payments
            else:
                max_loan = available_for_pi * (
                    (math.pow(1 + monthly_rate, num_payments) - 1) /
                    (monthly_rate * math.pow(1 + monthly_rate, num_payments))
                )

            # Update home value estimate
            estimated_home_value = max_loan + down_payment

        max_purchase_price = max_loan + down_payment

        # Verify with actual PITI calculation
        verification = self.calculate_piti(
            loan_amount=max_loan,
            interest_rate=interest_rate,
            term_years=term_years,
            property_value=max_purchase_price,
        )

        return {
            "max_purchase_price": round(max_purchase_price, 2),
            "max_loan_amount": round(max_loan, 2),
            "down_payment": round(down_payment, 2),
            "down_payment_percent": round((down_payment / max_purchase_price) * 100, 2) if max_purchase_price > 0 else 0,
            "estimated_monthly_payment": verification["total_piti"],
            "estimated_dti": round((verification["total_piti"] + monthly_debts) / monthly_income * 100, 2),
            "inputs": {
                "annual_income": annual_income,
                "monthly_debts": monthly_debts,
                "down_payment": down_payment,
                "interest_rate": interest_rate,
                "max_dti": max_dti * 100,
            },
        }

    def estimate_closing_costs(
        self,
        loan_amount: float,
        property_value: float,
        state: str = "CA",
        loan_type: str = "conventional",
    ) -> Dict[str, Any]:
        """
        Estimate closing costs for a purchase.

        Args:
            loan_amount: Loan amount in dollars
            property_value: Purchase price in dollars
            state: Two-letter state code
            loan_type: Loan type (affects some fees)

        Returns:
            Dict with itemized closing costs
        """
        # Get state-specific rate or default
        state_rate = STATE_CLOSING_COSTS.get(state.upper(), 0.03)

        # Lender fees (% of loan)
        origination_fee = loan_amount * 0.01  # 1%
        underwriting_fee = 500
        processing_fee = 450
        credit_report = 50
        flood_cert = 25

        # Third party fees
        appraisal = 550
        title_search = 200
        title_insurance = property_value * 0.005  # ~0.5% of purchase price
        settlement_fee = 750
        recording_fees = 150
        survey = 400

        # Prepaid items (estimate)
        prepaid_interest = (loan_amount * 0.065 / 365) * 15  # ~15 days
        prepaid_insurance = property_value * 0.0035  # 1 year
        prepaid_taxes = (property_value * DEFAULT_TAX_RATE) / 4  # 3 months

        # Escrow reserves
        escrow_insurance = prepaid_insurance / 6  # 2 months
        escrow_taxes = (property_value * DEFAULT_TAX_RATE) / 6  # 2 months

        # Loan-type specific fees
        if loan_type.lower() == "fha":
            upfront_mip = loan_amount * 0.0175
        elif loan_type.lower() == "va":
            upfront_mip = loan_amount * 0.0215  # First use, no down
        elif loan_type.lower() == "usda":
            upfront_mip = loan_amount * 0.01
        else:
            upfront_mip = 0

        # Calculate totals
        lender_fees = origination_fee + underwriting_fee + processing_fee + credit_report + flood_cert
        third_party_fees = appraisal + title_search + title_insurance + settlement_fee + recording_fees + survey
        prepaids = prepaid_interest + prepaid_insurance + prepaid_taxes
        escrows = escrow_insurance + escrow_taxes

        total_closing_costs = lender_fees + third_party_fees + prepaids + escrows + upfront_mip

        return {
            "total_closing_costs": round(total_closing_costs, 2),
            "lender_fees": {
                "origination": round(origination_fee, 2),
                "underwriting": round(underwriting_fee, 2),
                "processing": round(processing_fee, 2),
                "credit_report": round(credit_report, 2),
                "flood_cert": round(flood_cert, 2),
                "total": round(lender_fees, 2),
            },
            "third_party_fees": {
                "appraisal": round(appraisal, 2),
                "title_search": round(title_search, 2),
                "title_insurance": round(title_insurance, 2),
                "settlement": round(settlement_fee, 2),
                "recording": round(recording_fees, 2),
                "survey": round(survey, 2),
                "total": round(third_party_fees, 2),
            },
            "prepaids": {
                "interest": round(prepaid_interest, 2),
                "insurance": round(prepaid_insurance, 2),
                "taxes": round(prepaid_taxes, 2),
                "total": round(prepaids, 2),
            },
            "escrows": {
                "insurance": round(escrow_insurance, 2),
                "taxes": round(escrow_taxes, 2),
                "total": round(escrows, 2),
            },
            "upfront_mi": round(upfront_mip, 2),
            "inputs": {
                "loan_amount": loan_amount,
                "property_value": property_value,
                "state": state,
                "loan_type": loan_type,
            },
            "notes": f"Estimates based on {state} averages. Actual costs may vary.",
        }

    def generate_amortization(
        self,
        loan_amount: float,
        interest_rate: float,
        term_years: int = 30,
        num_payments: int = 12,
    ) -> List[Dict[str, Any]]:
        """
        Generate amortization schedule.

        Args:
            loan_amount: Loan amount in dollars
            interest_rate: Annual interest rate as percentage
            term_years: Loan term in years
            num_payments: Number of payments to include in schedule

        Returns:
            List of payment dictionaries with principal, interest, balance
        """
        monthly_rate = (interest_rate / 100) / 12
        total_payments = term_years * 12

        # Calculate monthly payment
        if monthly_rate == 0:
            monthly_payment = loan_amount / total_payments
        else:
            monthly_payment = (
                loan_amount * monthly_rate * math.pow(1 + monthly_rate, total_payments)
            ) / (math.pow(1 + monthly_rate, total_payments) - 1)

        schedule = []
        balance = loan_amount
        total_interest_paid = 0
        total_principal_paid = 0

        for month in range(1, min(num_payments + 1, total_payments + 1)):
            interest_payment = balance * monthly_rate
            principal_payment = monthly_payment - interest_payment
            balance -= principal_payment

            total_interest_paid += interest_payment
            total_principal_paid += principal_payment

            schedule.append({
                "payment_number": month,
                "payment": round(monthly_payment, 2),
                "principal": round(principal_payment, 2),
                "interest": round(interest_payment, 2),
                "balance": round(max(balance, 0), 2),
                "total_interest_paid": round(total_interest_paid, 2),
                "total_principal_paid": round(total_principal_paid, 2),
            })

        return schedule


    def calculate_cost_of_waiting(
        self,
        home_price: float,
        current_rate: float,
        down_payment_percent: float,
        current_rent: float,
        wait_months: int = 12,
        home_appreciation_rate: float = 4.0,
        rate_increase_per_year: float = 0.5,
        rent_increase_rate: float = 3.0,
        term_years: int = 30,
    ) -> Dict[str, Any]:
        """
        Calculate the cost of waiting to buy a home.

        Args:
            home_price: Current home price
            current_rate: Current mortgage interest rate (percentage)
            down_payment_percent: Down payment as percentage
            current_rent: Current monthly rent
            wait_months: Months to wait before buying
            home_appreciation_rate: Annual home appreciation rate (percentage)
            rate_increase_per_year: Expected rate increase per year (percentage points)
            rent_increase_rate: Annual rent increase rate (percentage)
            term_years: Loan term in years

        Returns:
            Dict with cost breakdown and comparison
        """
        wait_years = wait_months / 12

        # Calculate future home price
        future_price = home_price * math.pow(1 + (home_appreciation_rate / 100), wait_years)
        price_increase = future_price - home_price

        # Calculate future rate
        future_rate = current_rate + (rate_increase_per_year * wait_years)

        # Calculate down payments
        current_down = home_price * (down_payment_percent / 100)
        future_down = future_price * (down_payment_percent / 100)
        additional_down_needed = future_down - current_down

        # Calculate loan amounts
        current_loan = home_price - current_down
        future_loan = future_price - future_down

        # Calculate monthly payments
        current_pi = self.calculate_monthly_pi(current_loan, current_rate, term_years)
        future_pi = self.calculate_monthly_pi(future_loan, future_rate, term_years)

        monthly_payment_increase = future_pi["monthly_payment"] - current_pi["monthly_payment"]
        total_interest_increase = future_pi["total_interest"] - current_pi["total_interest"]

        # Calculate rent paid while waiting
        total_rent = 0
        monthly_rent = current_rent
        for month in range(wait_months):
            if month > 0 and month % 12 == 0:
                monthly_rent *= (1 + rent_increase_rate / 100)
            total_rent += monthly_rent

        # Calculate equity lost (appreciation + principal paydown)
        # Simplified: just appreciation since no ownership
        equity_missed = price_increase

        # Total cost of waiting
        total_cost = price_increase + total_interest_increase + total_rent

        return {
            "wait_months": wait_months,
            "buy_now": {
                "home_price": round(home_price, 2),
                "down_payment": round(current_down, 2),
                "loan_amount": round(current_loan, 2),
                "interest_rate": current_rate,
                "monthly_payment": current_pi["monthly_payment"],
                "total_interest": current_pi["total_interest"],
            },
            "buy_later": {
                "home_price": round(future_price, 2),
                "down_payment": round(future_down, 2),
                "loan_amount": round(future_loan, 2),
                "interest_rate": round(future_rate, 3),
                "monthly_payment": future_pi["monthly_payment"],
                "total_interest": future_pi["total_interest"],
            },
            "costs": {
                "price_increase": round(price_increase, 2),
                "additional_down_payment": round(additional_down_needed, 2),
                "monthly_payment_increase": round(monthly_payment_increase, 2),
                "total_interest_increase": round(total_interest_increase, 2),
                "rent_paid_while_waiting": round(total_rent, 2),
                "equity_missed": round(equity_missed, 2),
            },
            "total_cost_of_waiting": round(total_cost, 2),
            "assumptions": {
                "home_appreciation_rate": home_appreciation_rate,
                "rate_increase_per_year": rate_increase_per_year,
                "rent_increase_rate": rent_increase_rate,
            },
            "recommendation": "buy_now" if total_cost > 0 else "wait",
            "notes": f"Waiting {wait_months} months could cost ${total_cost:,.0f} in higher prices, "
                     f"increased interest, and rent paid.",
        }

    def calculate_prepay_vs_invest(
        self,
        loan_balance: float,
        interest_rate: float,
        remaining_years: int,
        extra_monthly: float,
        expected_return: float = 7.0,
        projection_years: int = 10,
    ) -> Dict[str, Any]:
        """
        Compare mortgage prepayment vs investing extra cash.

        Args:
            loan_balance: Current loan balance
            interest_rate: Mortgage interest rate (percentage)
            remaining_years: Remaining loan term in years
            extra_monthly: Extra monthly cash available
            expected_return: Expected annual investment return (percentage)
            projection_years: Years to project forward

        Returns:
            Dict with prepay and invest scenarios compared
        """
        monthly_rate = (interest_rate / 100) / 12
        total_payments = remaining_years * 12

        # Calculate base monthly payment
        if monthly_rate == 0:
            base_payment = loan_balance / total_payments
        else:
            base_payment = (
                loan_balance * monthly_rate * math.pow(1 + monthly_rate, total_payments)
            ) / (math.pow(1 + monthly_rate, total_payments) - 1)

        # Scenario 1: Prepay mortgage
        prepay_balance = loan_balance
        prepay_months = 0
        prepay_total_interest = 0
        prepay_total_paid = 0

        while prepay_balance > 0 and prepay_months < total_payments:
            interest_portion = prepay_balance * monthly_rate
            principal_portion = base_payment - interest_portion + extra_monthly

            if principal_portion > prepay_balance:
                principal_portion = prepay_balance + interest_portion
                prepay_total_paid += prepay_balance + interest_portion
                prepay_total_interest += interest_portion
                prepay_balance = 0
            else:
                prepay_balance -= (base_payment + extra_monthly - interest_portion)
                prepay_total_interest += interest_portion
                prepay_total_paid += base_payment + extra_monthly

            prepay_months += 1

        years_saved = (total_payments - prepay_months) / 12

        # Calculate interest saved vs normal payoff
        normal_total_interest = (base_payment * total_payments) - loan_balance
        interest_saved = normal_total_interest - prepay_total_interest

        # Scenario 2: Invest the extra cash
        invest_monthly_return = (expected_return / 100) / 12
        invest_portfolio = 0
        invest_months = 0
        invest_balance = loan_balance
        invest_total_interest = 0

        # Track year-by-year for comparison
        yearly_comparison = []

        for year in range(1, projection_years + 1):
            year_start_portfolio = invest_portfolio
            year_start_prepay_balance = prepay_balance if prepay_months > (year - 1) * 12 else 0

            for month in range((year - 1) * 12, min(year * 12, total_payments)):
                # Investment grows
                invest_portfolio = invest_portfolio * (1 + invest_monthly_return) + extra_monthly

                # Normal mortgage continues
                if invest_balance > 0:
                    interest_portion = invest_balance * monthly_rate
                    principal_portion = base_payment - interest_portion
                    invest_balance -= principal_portion
                    invest_total_interest += interest_portion

            # Calculate prepay balance at this point
            temp_balance = loan_balance
            for m in range(min(year * 12, prepay_months)):
                interest_p = temp_balance * monthly_rate
                principal_p = base_payment + extra_monthly - interest_p
                temp_balance = max(0, temp_balance - principal_p)

            yearly_comparison.append({
                "year": year,
                "prepay_remaining_balance": round(max(0, temp_balance), 2),
                "prepay_equity_gained": round(loan_balance - max(0, temp_balance), 2),
                "invest_portfolio_value": round(invest_portfolio, 2),
                "invest_remaining_balance": round(max(0, invest_balance), 2),
                "invest_net_worth_gain": round(invest_portfolio + (loan_balance - max(0, invest_balance)), 2),
            })

        # Final comparison at projection end
        final_prepay_equity = loan_balance - max(0, temp_balance)
        final_invest_value = invest_portfolio + (loan_balance - max(0, invest_balance))

        winner = "invest" if invest_portfolio > interest_saved else "prepay"
        advantage = abs(invest_portfolio - interest_saved)

        # Calculate breakeven return rate
        # At what return rate would investing equal prepay benefit?
        breakeven_rate = interest_rate  # Simplified approximation

        return {
            "prepay_scenario": {
                "strategy": "Extra payments toward mortgage",
                "monthly_extra": round(extra_monthly, 2),
                "payoff_months": prepay_months,
                "years_saved": round(years_saved, 1),
                "total_interest_paid": round(prepay_total_interest, 2),
                "interest_saved": round(interest_saved, 2),
                "effective_return": round(interest_rate, 2),  # Guaranteed return
            },
            "invest_scenario": {
                "strategy": "Invest in market",
                "monthly_investment": round(extra_monthly, 2),
                "portfolio_value": round(invest_portfolio, 2),
                "expected_return": expected_return,
                "total_interest_paid": round(invest_total_interest, 2),
                "net_gain": round(invest_portfolio - (extra_monthly * projection_years * 12), 2),
            },
            "comparison": {
                "winner": winner,
                "advantage_amount": round(advantage, 2),
                "breakeven_return": round(breakeven_rate, 2),
                "yearly_breakdown": yearly_comparison,
            },
            "inputs": {
                "loan_balance": loan_balance,
                "interest_rate": interest_rate,
                "remaining_years": remaining_years,
                "extra_monthly": extra_monthly,
                "expected_return": expected_return,
                "projection_years": projection_years,
            },
            "recommendation": winner,
            "notes": f"{'Investing' if winner == 'invest' else 'Prepaying'} wins by ${advantage:,.0f} "
                     f"over {projection_years} years. "
                     f"Prepaying offers guaranteed {interest_rate}% return; "
                     f"investing assumes {expected_return}% return with market risk.",
        }

    def calculate_rent_vs_buy(
        self,
        home_price: float,
        down_payment_percent: float,
        interest_rate: float,
        monthly_rent: float,
        term_years: int = 30,
        home_appreciation: float = 3.0,
        rent_increase: float = 3.0,
        investment_return: float = 7.0,
        property_tax_rate: float = 1.07,
        insurance_rate: float = 0.35,
        maintenance_rate: float = 1.0,
        projection_years: int = 10,
    ) -> Dict[str, Any]:
        """
        Comprehensive rent vs buy analysis with net worth projection.

        Args:
            home_price: Purchase price
            down_payment_percent: Down payment as percentage
            interest_rate: Mortgage rate (percentage)
            monthly_rent: Current monthly rent
            term_years: Loan term
            home_appreciation: Annual home value increase (percentage)
            rent_increase: Annual rent increase (percentage)
            investment_return: Return on invested down payment if renting (percentage)
            property_tax_rate: Annual property tax as percentage of value
            insurance_rate: Annual insurance as percentage of value
            maintenance_rate: Annual maintenance as percentage of value
            projection_years: Years to project

        Returns:
            Dict with comprehensive comparison
        """
        down_payment = home_price * (down_payment_percent / 100)
        loan_amount = home_price - down_payment

        # Monthly costs for buying
        pi_result = self.calculate_monthly_pi(loan_amount, interest_rate, term_years)
        monthly_pi = pi_result["monthly_payment"]
        monthly_tax = (home_price * (property_tax_rate / 100)) / 12
        monthly_insurance = (home_price * (insurance_rate / 100)) / 12
        monthly_maintenance = (home_price * (maintenance_rate / 100)) / 12

        # Calculate PMI if applicable
        ltv = (loan_amount / home_price) * 100
        monthly_pmi = 0
        if ltv > 80:
            pmi_result = self.calculate_pmi(loan_amount, home_price)
            monthly_pmi = pmi_result.get("monthly_premium", 0)

        initial_buy_monthly = monthly_pi + monthly_tax + monthly_insurance + monthly_maintenance + monthly_pmi

        # Year by year projection
        yearly_projection = []
        buy_total_cost = down_payment  # Initial investment
        rent_total_cost = 0
        rent_investment_value = down_payment  # What renter invests instead

        home_value = home_price
        loan_balance = loan_amount
        current_rent = monthly_rent

        monthly_invest_return = (investment_return / 100) / 12
        monthly_mortgage_rate = (interest_rate / 100) / 12

        for year in range(1, projection_years + 1):
            # Update values for the year
            year_buy_cost = 0
            year_rent_cost = 0

            for month in range(12):
                # Buying costs
                interest_payment = loan_balance * monthly_mortgage_rate
                principal_payment = monthly_pi - interest_payment
                loan_balance -= principal_payment

                # Update PMI - drops when LTV reaches 80%
                current_ltv = (loan_balance / home_value) * 100
                current_pmi = monthly_pmi if current_ltv > 80 else 0

                year_buy_cost += monthly_pi + monthly_tax + monthly_insurance + monthly_maintenance + current_pmi

                # Renting costs
                year_rent_cost += current_rent

                # Renter's investment grows
                rent_investment_value = rent_investment_value * (1 + monthly_invest_return)
                # Add monthly savings difference (if any) to investment
                monthly_savings = (monthly_pi + monthly_tax + monthly_insurance + monthly_maintenance + current_pmi) - current_rent
                if monthly_savings > 0:
                    rent_investment_value += monthly_savings

            # Annual appreciation
            home_value *= (1 + home_appreciation / 100)

            # Annual rent increase
            current_rent *= (1 + rent_increase / 100)

            # Update yearly costs
            buy_total_cost += year_buy_cost
            rent_total_cost += year_rent_cost

            # Calculate equity
            home_equity = home_value - loan_balance

            yearly_projection.append({
                "year": year,
                "buy": {
                    "home_value": round(home_value, 2),
                    "loan_balance": round(loan_balance, 2),
                    "equity": round(home_equity, 2),
                    "year_cost": round(year_buy_cost, 2),
                    "total_cost": round(buy_total_cost, 2),
                    "net_worth_gain": round(home_equity - down_payment, 2),
                },
                "rent": {
                    "monthly_rent": round(current_rent, 2),
                    "year_cost": round(year_rent_cost, 2),
                    "total_cost": round(rent_total_cost, 2),
                    "investment_value": round(rent_investment_value, 2),
                    "net_worth_gain": round(rent_investment_value - down_payment, 2),
                },
            })

        # Final comparison
        final_buy_equity = home_value - loan_balance
        final_rent_wealth = rent_investment_value

        winner = "buy" if final_buy_equity > final_rent_wealth else "rent"
        advantage = abs(final_buy_equity - final_rent_wealth)

        # Calculate breakeven year
        breakeven_year = None
        for proj in yearly_projection:
            if proj["buy"]["equity"] > proj["rent"]["investment_value"]:
                breakeven_year = proj["year"]
                break

        return {
            "summary": {
                "winner": winner,
                "advantage": round(advantage, 2),
                "breakeven_year": breakeven_year,
                "buy_equity_at_end": round(final_buy_equity, 2),
                "rent_wealth_at_end": round(final_rent_wealth, 2),
            },
            "initial_comparison": {
                "buy_monthly": round(initial_buy_monthly, 2),
                "rent_monthly": round(monthly_rent, 2),
                "difference": round(initial_buy_monthly - monthly_rent, 2),
            },
            "yearly_projection": yearly_projection,
            "inputs": {
                "home_price": home_price,
                "down_payment_percent": down_payment_percent,
                "interest_rate": interest_rate,
                "monthly_rent": monthly_rent,
                "home_appreciation": home_appreciation,
                "rent_increase": rent_increase,
                "investment_return": investment_return,
                "projection_years": projection_years,
            },
            "recommendation": winner,
            "notes": f"Over {projection_years} years, {'buying' if winner == 'buy' else 'renting'} "
                     f"builds ${advantage:,.0f} more wealth. "
                     + (f"Buying breaks even at year {breakeven_year}." if breakeven_year else ""),
        }

    def evaluate_loan_programs(
        self,
        home_price: float,
        down_payment_available: float,
        annual_income: float,
        credit_score: int,
        monthly_debts: float,
        is_first_time_buyer: bool = True,
        is_veteran: bool = False,
        is_va_disabled: bool = False,
        property_state: str = "CA",
        property_county: str = None,
        is_rural: bool = False,
    ) -> Dict[str, Any]:
        """
        Evaluate eligibility and compare loan programs.

        Args:
            home_price: Purchase price
            down_payment_available: Cash available for down payment
            annual_income: Gross annual income
            credit_score: Credit score
            monthly_debts: Monthly debt payments
            is_first_time_buyer: First time homebuyer status
            is_veteran: VA eligibility
            is_va_disabled: VA disability exemption
            property_state: Property state code
            property_county: Property county
            is_rural: USDA rural area eligibility

        Returns:
            Dict with program comparisons and recommendations
        """
        programs = []
        monthly_income = annual_income / 12

        # Define program requirements
        program_defs = {
            "conventional_20": {
                "name": "Conventional 20% Down",
                "min_down_pct": 20.0,
                "min_credit": 620,
                "max_dti": 45,
                "has_pmi": False,
            },
            "conventional_10": {
                "name": "Conventional 10% Down",
                "min_down_pct": 10.0,
                "min_credit": 620,
                "max_dti": 45,
                "has_pmi": True,
            },
            "conventional_5": {
                "name": "Conventional 5% Down",
                "min_down_pct": 5.0,
                "min_credit": 620,
                "max_dti": 45,
                "has_pmi": True,
            },
            "conventional_3": {
                "name": "Conventional 3% Down",
                "min_down_pct": 3.0,
                "min_credit": 620,
                "max_dti": 45,
                "has_pmi": True,
                "first_time_only": True,
            },
            "fha": {
                "name": "FHA Loan",
                "min_down_pct": 3.5,
                "min_credit": 580,
                "min_credit_10_down": 500,
                "max_dti": 50,
                "has_mip": True,
            },
            "va": {
                "name": "VA Loan",
                "min_down_pct": 0.0,
                "min_credit": 620,
                "max_dti": 41,
                "veteran_required": True,
                "has_funding_fee": True,
            },
            "usda": {
                "name": "USDA Loan",
                "min_down_pct": 0.0,
                "min_credit": 640,
                "max_dti": 41,
                "rural_required": True,
                "income_limit": True,
                "has_guarantee_fee": True,
            },
        }

        # Evaluate each program
        for prog_id, prog in program_defs.items():
            eligible = True
            issues = []
            advantages = []
            disadvantages = []

            min_down = home_price * (prog["min_down_pct"] / 100)

            # Check down payment
            if down_payment_available < min_down:
                eligible = False
                issues.append(f"Need ${min_down:,.0f} down payment (have ${down_payment_available:,.0f})")

            # Check credit score
            min_credit = prog.get("min_credit", 620)
            if prog_id == "fha" and down_payment_available >= home_price * 0.10:
                min_credit = prog.get("min_credit_10_down", 500)

            if credit_score < min_credit:
                eligible = False
                issues.append(f"Minimum credit score is {min_credit} (have {credit_score})")

            # Check first-time buyer requirement
            if prog.get("first_time_only") and not is_first_time_buyer:
                eligible = False
                issues.append("First-time homebuyer required")

            # Check veteran requirement
            if prog.get("veteran_required") and not is_veteran:
                eligible = False
                issues.append("VA eligibility required")

            # Check rural requirement
            if prog.get("rural_required") and not is_rural:
                eligible = False
                issues.append("Property must be in USDA-eligible rural area")

            # Calculate payment and DTI if eligible
            if eligible:
                down = max(min_down, down_payment_available) if prog["min_down_pct"] > 0 else 0
                loan_amount = home_price - down

                # Use average rate (simplified)
                rate = 6.5  # Would come from rate service in production

                piti = self.calculate_piti(
                    loan_amount=loan_amount,
                    interest_rate=rate,
                    term_years=30,
                    property_value=home_price,
                    credit_score=credit_score,
                    loan_type=prog_id.split("_")[0],
                )

                # Check DTI
                front_dti = (piti["total_piti"] / monthly_income) * 100
                back_dti = ((piti["total_piti"] + monthly_debts) / monthly_income) * 100

                if back_dti > prog["max_dti"]:
                    eligible = False
                    issues.append(f"DTI {back_dti:.1f}% exceeds {prog['max_dti']}% limit")

                # Add program details
                program_data = {
                    "id": prog_id,
                    "name": prog["name"],
                    "eligible": eligible,
                    "issues": issues,
                    "down_payment_required": round(min_down, 2),
                    "down_payment_percent": prog["min_down_pct"],
                }

                if eligible:
                    program_data.update({
                        "loan_amount": round(loan_amount, 2),
                        "monthly_payment": piti["total_piti"],
                        "principal_interest": piti["principal_interest"],
                        "monthly_pmi_mip": piti["pmi_monthly"],
                        "front_end_dti": round(front_dti, 1),
                        "back_end_dti": round(back_dti, 1),
                    })

                    # Add advantages/disadvantages
                    if prog["min_down_pct"] == 0:
                        advantages.append("No down payment required")
                    if prog["min_down_pct"] <= 3.5:
                        advantages.append("Low down payment option")
                    if not prog.get("has_pmi") and not prog.get("has_mip"):
                        advantages.append("No ongoing mortgage insurance")
                    if prog_id == "va":
                        advantages.append("No monthly MI, just one-time funding fee")
                        if is_va_disabled:
                            advantages.append("VA funding fee waived due to disability")
                    if prog.get("has_pmi"):
                        disadvantages.append("PMI required until 20% equity")
                    if prog.get("has_mip"):
                        disadvantages.append("FHA MIP may be for life of loan")

                    program_data["advantages"] = advantages
                    program_data["disadvantages"] = disadvantages

                programs.append(program_data)

        # Sort by eligibility and monthly payment
        eligible_programs = [p for p in programs if p["eligible"]]
        ineligible_programs = [p for p in programs if not p["eligible"]]

        eligible_programs.sort(key=lambda x: x.get("monthly_payment", float("inf")))

        recommended = eligible_programs[0] if eligible_programs else None

        return {
            "eligible_programs": eligible_programs,
            "ineligible_programs": ineligible_programs,
            "recommended": recommended["id"] if recommended else None,
            "recommended_program": recommended,
            "borrower_profile": {
                "home_price": home_price,
                "down_payment_available": down_payment_available,
                "credit_score": credit_score,
                "annual_income": annual_income,
                "monthly_debts": monthly_debts,
                "is_first_time_buyer": is_first_time_buyer,
                "is_veteran": is_veteran,
            },
            "notes": f"Found {len(eligible_programs)} eligible programs. "
                     + (f"Recommended: {recommended['name']}" if recommended else "No eligible programs found."),
        }


# Singleton instance for easy import
calculator_service = MortgageCalculatorService()
