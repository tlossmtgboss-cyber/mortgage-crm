"""
Pre-Qualification Calculator

Calculates loan eligibility, DTI ratios, LTV, estimated rates, and
maximum loan amounts from extracted call data.

This is used by the CallIntelligenceOrchestrator to provide instant
pre-qualification results after a call.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# =============================================================================
# Enums and Constants
# =============================================================================

class LoanProgram(str, Enum):
    """Available loan programs."""
    CONVENTIONAL = "conventional"
    FHA = "fha"
    VA = "va"
    USDA = "usda"
    JUMBO = "jumbo"


class QualificationStatus(str, Enum):
    """Pre-qualification status."""
    QUALIFIED = "qualified"
    CONDITIONALLY_QUALIFIED = "conditionally_qualified"
    NOT_QUALIFIED = "not_qualified"
    INSUFFICIENT_DATA = "insufficient_data"


# Loan program limits and requirements
CONFORMING_LOAN_LIMIT = 832750  # 2026 conforming loan limit
CONFORMING_HIGH_COST_LIMIT = 1249125  # High-cost area limit

PROGRAM_REQUIREMENTS = {
    LoanProgram.CONVENTIONAL: {
        "min_credit_score": 620,
        "max_dti": 45,
        "max_ltv": 97,
        "min_down_payment_pct": 3,
        "max_loan_amount": CONFORMING_LOAN_LIMIT,
    },
    LoanProgram.FHA: {
        "min_credit_score": 580,
        "max_dti": 50,
        "max_ltv": 96.5,
        "min_down_payment_pct": 3.5,
        "max_loan_amount": CONFORMING_LOAN_LIMIT,
        "mip_upfront_pct": 1.75,
        "mip_annual_pct": 0.85,
    },
    LoanProgram.VA: {
        "min_credit_score": 580,
        "max_dti": 60,
        "max_ltv": 100,
        "min_down_payment_pct": 0,
        "max_loan_amount": None,  # No limit for eligible veterans
        "funding_fee_pct": 2.15,  # First use, no down payment
    },
    LoanProgram.USDA: {
        "min_credit_score": 640,
        "max_dti": 41,
        "max_ltv": 100,
        "min_down_payment_pct": 0,
        "max_loan_amount": None,  # Based on area
        "guarantee_fee_pct": 1.0,
        "annual_fee_pct": 0.35,
    },
    LoanProgram.JUMBO: {
        "min_credit_score": 700,
        "max_dti": 43,
        "max_ltv": 80,
        "min_down_payment_pct": 20,
        "min_loan_amount": CONFORMING_LOAN_LIMIT + 1,
    },
}

# Base rates by credit score tier (simplified - would integrate with rate engine)
BASE_RATES = {
    "excellent": 6.50,   # 760+
    "good": 6.75,        # 700-759
    "fair": 7.25,        # 660-699
    "poor": 7.75,        # 620-659
}


@dataclass
class IncomeBreakdown:
    """Breakdown of income sources."""
    base_salary: Decimal = Decimal("0")
    bonus: Decimal = Decimal("0")
    commission: Decimal = Decimal("0")
    overtime: Decimal = Decimal("0")
    rental: Decimal = Decimal("0")
    other: Decimal = Decimal("0")

    @property
    def total_monthly(self) -> Decimal:
        """Total monthly income."""
        return self.base_salary + self.bonus + self.commission + self.overtime + self.rental + self.other

    @property
    def total_annual(self) -> Decimal:
        """Total annual income."""
        return self.total_monthly * 12


@dataclass
class DebtBreakdown:
    """Breakdown of monthly debt obligations."""
    car_payment: Decimal = Decimal("0")
    student_loans: Decimal = Decimal("0")
    credit_cards: Decimal = Decimal("0")
    other_loans: Decimal = Decimal("0")
    alimony: Decimal = Decimal("0")
    child_support: Decimal = Decimal("0")

    @property
    def total_monthly(self) -> Decimal:
        """Total monthly debt payments."""
        return (self.car_payment + self.student_loans + self.credit_cards +
                self.other_loans + self.alimony + self.child_support)


@dataclass
class PreQualificationResult:
    """Result of pre-qualification calculation."""

    # Status
    status: QualificationStatus
    qualified_programs: List[LoanProgram] = field(default_factory=list)

    # Key metrics
    max_purchase_price: Decimal = Decimal("0")
    max_loan_amount: Decimal = Decimal("0")
    estimated_monthly_payment: Decimal = Decimal("0")
    estimated_rate: float = 0.0

    # Ratios
    front_end_dti: float = 0.0  # Housing expense / income
    back_end_dti: float = 0.0   # Total debt / income
    ltv: float = 0.0

    # Income and debt
    monthly_income: Decimal = Decimal("0")
    monthly_debt: Decimal = Decimal("0")

    # Down payment
    down_payment: Decimal = Decimal("0")
    down_payment_pct: float = 0.0

    # Assets
    total_assets: Decimal = Decimal("0")
    months_reserves: int = 0

    # Credit
    estimated_credit_score: Optional[int] = None
    credit_tier: str = "unknown"

    # Recommendations
    recommendations: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    # Metadata
    calculated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    data_completeness: float = 0.0  # Percentage of required data available

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status.value,
            "qualified_programs": [p.value for p in self.qualified_programs],
            "max_purchase_price": float(self.max_purchase_price),
            "max_loan_amount": float(self.max_loan_amount),
            "estimated_monthly_payment": float(self.estimated_monthly_payment),
            "estimated_rate": self.estimated_rate,
            "front_end_dti": round(self.front_end_dti, 1),
            "back_end_dti": round(self.back_end_dti, 1),
            "ltv": round(self.ltv, 1),
            "monthly_income": float(self.monthly_income),
            "monthly_debt": float(self.monthly_debt),
            "down_payment": float(self.down_payment),
            "down_payment_pct": round(self.down_payment_pct, 1),
            "total_assets": float(self.total_assets),
            "months_reserves": self.months_reserves,
            "estimated_credit_score": self.estimated_credit_score,
            "credit_tier": self.credit_tier,
            "recommendations": self.recommendations,
            "warnings": self.warnings,
            "calculated_at": self.calculated_at.isoformat(),
            "data_completeness": round(self.data_completeness, 1),
        }


class PreQualificationCalculator:
    """
    Calculate pre-qualification based on extracted call data.

    Usage:
        calculator = PreQualificationCalculator()
        result = calculator.calculate(extracted_data)

        print(f"Status: {result.status}")
        print(f"Max purchase price: ${result.max_purchase_price:,.2f}")
        print(f"Qualified for: {result.qualified_programs}")
    """

    def __init__(self, property_tax_rate: float = 1.2, insurance_rate: float = 0.5):
        """
        Initialize calculator.

        Args:
            property_tax_rate: Annual property tax as % of home value
            insurance_rate: Annual insurance as % of home value
        """
        self.property_tax_rate = property_tax_rate / 100 / 12  # Monthly rate
        self.insurance_rate = insurance_rate / 100 / 12  # Monthly rate

    def calculate(
        self,
        extracted_data: Dict[str, Any],
        target_purchase_price: Optional[Decimal] = None,
        preferred_program: Optional[LoanProgram] = None,
    ) -> PreQualificationResult:
        """
        Calculate pre-qualification from extracted call data.

        Args:
            extracted_data: Data extracted from call (identity, financial, etc.)
            target_purchase_price: Specific purchase price to qualify for
            preferred_program: Preferred loan program

        Returns:
            PreQualificationResult with qualification details
        """
        result = PreQualificationResult(status=QualificationStatus.INSUFFICIENT_DATA)

        # Extract and normalize data
        income = self._extract_income(extracted_data)
        debts = self._extract_debts(extracted_data)
        assets = self._extract_assets(extracted_data)
        credit_score = self._extract_credit_score(extracted_data)
        down_payment = self._extract_down_payment(extracted_data)
        purchase_price = target_purchase_price or self._extract_purchase_price(extracted_data)

        # Calculate data completeness
        result.data_completeness = self._calculate_completeness(
            income, debts, assets, credit_score, down_payment, purchase_price
        )

        # Store basic metrics
        result.monthly_income = income.total_monthly
        result.monthly_debt = debts.total_monthly
        result.total_assets = assets
        result.down_payment = down_payment
        result.estimated_credit_score = credit_score
        result.credit_tier = self._get_credit_tier(credit_score)

        # Need minimum data to calculate
        if income.total_monthly <= 0:
            result.warnings.append("No income data available")
            return result

        # Get estimated rate based on credit
        result.estimated_rate = self._estimate_rate(credit_score)

        # Calculate for each loan program
        program_results = {}
        for program in LoanProgram:
            program_result = self._calculate_for_program(
                program=program,
                income=income,
                debts=debts,
                assets=assets,
                credit_score=credit_score,
                down_payment=down_payment,
                purchase_price=purchase_price,
                rate=result.estimated_rate,
            )
            program_results[program] = program_result

            if program_result["qualified"]:
                result.qualified_programs.append(program)

        # Determine overall status
        if result.qualified_programs:
            result.status = QualificationStatus.QUALIFIED
        elif any(r.get("conditionally_qualified") for r in program_results.values()):
            result.status = QualificationStatus.CONDITIONALLY_QUALIFIED
        elif result.data_completeness < 50:
            result.status = QualificationStatus.INSUFFICIENT_DATA
        else:
            result.status = QualificationStatus.NOT_QUALIFIED

        # Calculate max amounts based on best qualifying program
        if result.qualified_programs:
            best_program = self._select_best_program(result.qualified_programs, preferred_program)
            best_result = program_results[best_program]

            result.max_loan_amount = Decimal(str(best_result["max_loan_amount"]))
            result.max_purchase_price = Decimal(str(best_result["max_purchase_price"]))
            result.estimated_monthly_payment = Decimal(str(best_result["monthly_payment"]))
            result.front_end_dti = best_result["front_end_dti"]
            result.back_end_dti = best_result["back_end_dti"]
            result.ltv = best_result["ltv"]
            result.down_payment_pct = best_result["down_payment_pct"]

        # Calculate reserves
        if result.estimated_monthly_payment > 0:
            result.months_reserves = int(assets / result.estimated_monthly_payment)

        # Generate recommendations
        result.recommendations = self._generate_recommendations(
            result, program_results, credit_score, income, debts, assets
        )

        logger.info(
            f"Pre-qual calculated: {result.status.value}, "
            f"max ${result.max_purchase_price:,.0f}, "
            f"programs: {[p.value for p in result.qualified_programs]}"
        )

        return result

    def _extract_income(self, data: Dict[str, Any]) -> IncomeBreakdown:
        """Extract income from call data."""
        income = IncomeBreakdown()

        # Get income extractions
        income_data = data.get("income", {})
        employment_data = data.get("employment", {})

        # Base salary (try annual first, then monthly)
        annual_salary = self._to_decimal(income_data.get("annual_salary"))
        monthly_salary = self._to_decimal(income_data.get("monthly_salary"))

        if annual_salary > 0:
            income.base_salary = annual_salary / 12
        elif monthly_salary > 0:
            income.base_salary = monthly_salary

        # Other income sources (convert annual to monthly)
        income.bonus = self._to_decimal(income_data.get("bonus_income", 0)) / 12
        income.commission = self._to_decimal(income_data.get("commission_income", 0)) / 12
        income.overtime = self._to_decimal(income_data.get("overtime_income", 0)) / 12
        income.rental = self._to_decimal(income_data.get("rental_income", 0))  # Already monthly
        income.other = self._to_decimal(income_data.get("other_income", 0)) / 12

        return income

    def _extract_debts(self, data: Dict[str, Any]) -> DebtBreakdown:
        """Extract debts from call data."""
        debts = DebtBreakdown()

        # Get from liabilities or income data
        liabilities = data.get("liabilities", {})
        income_data = data.get("income", {})
        declarations = data.get("declarations", {})

        debts.car_payment = self._to_decimal(liabilities.get("car_payment") or income_data.get("car_payment"))
        debts.student_loans = self._to_decimal(liabilities.get("student_loan_payment") or income_data.get("student_loan_payment"))
        debts.credit_cards = self._to_decimal(liabilities.get("credit_card_payment") or income_data.get("credit_card_payment"))
        debts.other_loans = self._to_decimal(liabilities.get("other_debt_payment") or income_data.get("other_debt_payment"))
        debts.alimony = self._to_decimal(declarations.get("alimony_amount", 0))

        return debts

    def _extract_assets(self, data: Dict[str, Any]) -> Decimal:
        """Extract total assets from call data."""
        assets_data = data.get("assets", {})
        income_data = data.get("income", {})

        total = Decimal("0")
        total += self._to_decimal(assets_data.get("checking_balance") or income_data.get("checking_balance"))
        total += self._to_decimal(assets_data.get("savings_balance") or income_data.get("savings_balance"))
        total += self._to_decimal(assets_data.get("retirement_balance") or income_data.get("retirement_balance"))
        total += self._to_decimal(assets_data.get("investment_balance") or income_data.get("investment_balance"))
        total += self._to_decimal(assets_data.get("gift_funds") or income_data.get("gift_funds"))

        return total

    def _extract_credit_score(self, data: Dict[str, Any]) -> Optional[int]:
        """Extract estimated credit score."""
        identity = data.get("identity", {})
        return identity.get("estimated_credit_score")

    def _extract_down_payment(self, data: Dict[str, Any]) -> Decimal:
        """Extract down payment amount."""
        address_data = data.get("address", {})
        return self._to_decimal(address_data.get("down_payment", 0))

    def _extract_purchase_price(self, data: Dict[str, Any]) -> Optional[Decimal]:
        """Extract target purchase price."""
        address_data = data.get("address", {})
        price = self._to_decimal(address_data.get("purchase_price"))
        return price if price > 0 else None

    def _to_decimal(self, value: Any) -> Decimal:
        """Convert value to Decimal safely."""
        if value is None:
            return Decimal("0")
        try:
            return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        except (ValueError, TypeError):
            return Decimal("0")

    def _calculate_completeness(
        self,
        income: IncomeBreakdown,
        debts: DebtBreakdown,
        assets: Decimal,
        credit_score: Optional[int],
        down_payment: Decimal,
        purchase_price: Optional[Decimal],
    ) -> float:
        """Calculate data completeness percentage."""
        total_fields = 6
        complete = 0

        if income.total_monthly > 0:
            complete += 1
        if debts.total_monthly >= 0:  # 0 debt is valid
            complete += 1
        if assets > 0:
            complete += 1
        if credit_score is not None:
            complete += 1
        if down_payment > 0:
            complete += 1
        if purchase_price is not None and purchase_price > 0:
            complete += 1

        return (complete / total_fields) * 100

    def _get_credit_tier(self, credit_score: Optional[int]) -> str:
        """Get credit tier from score."""
        if credit_score is None:
            return "unknown"
        if credit_score >= 760:
            return "excellent"
        if credit_score >= 700:
            return "good"
        if credit_score >= 660:
            return "fair"
        return "poor"

    def _estimate_rate(self, credit_score: Optional[int]) -> float:
        """Estimate interest rate based on credit score."""
        tier = self._get_credit_tier(credit_score)
        return BASE_RATES.get(tier, BASE_RATES["fair"])

    def _calculate_for_program(
        self,
        program: LoanProgram,
        income: IncomeBreakdown,
        debts: DebtBreakdown,
        assets: Decimal,
        credit_score: Optional[int],
        down_payment: Decimal,
        purchase_price: Optional[Decimal],
        rate: float,
    ) -> Dict[str, Any]:
        """Calculate qualification for a specific program."""
        reqs = PROGRAM_REQUIREMENTS[program]
        result = {
            "program": program.value,
            "qualified": False,
            "conditionally_qualified": False,
            "max_loan_amount": 0,
            "max_purchase_price": 0,
            "monthly_payment": 0,
            "front_end_dti": 0,
            "back_end_dti": 0,
            "ltv": 0,
            "down_payment_pct": 0,
            "disqualifying_reasons": [],
        }

        monthly_income = float(income.total_monthly)
        monthly_debt = float(debts.total_monthly)

        if monthly_income <= 0:
            result["disqualifying_reasons"].append("No income")
            return result

        # Check credit score
        if credit_score is not None and credit_score < reqs["min_credit_score"]:
            result["disqualifying_reasons"].append(
                f"Credit score {credit_score} below minimum {reqs['min_credit_score']}"
            )

        # Calculate max housing payment based on DTI
        max_dti = reqs["max_dti"] / 100
        max_total_payment = monthly_income * max_dti
        max_housing_payment = max_total_payment - monthly_debt

        if max_housing_payment <= 0:
            result["disqualifying_reasons"].append("Debt too high for income")
            return result

        # Estimate max loan from max payment (simplified)
        # Payment = Principal * (rate/12 * (1+rate/12)^n) / ((1+rate/12)^n - 1)
        monthly_rate = rate / 100 / 12
        n = 360  # 30-year term

        if monthly_rate > 0:
            # Solve for principal from payment
            factor = (monthly_rate * (1 + monthly_rate) ** n) / ((1 + monthly_rate) ** n - 1)

            # Account for taxes and insurance (rough estimate)
            # Assume 70% of payment goes to P&I, 30% to taxes/insurance
            pi_payment = max_housing_payment * 0.70
            max_loan = pi_payment / factor
        else:
            max_loan = max_housing_payment * 300  # Rough estimate for 0% rate

        # Apply program loan limits
        program_max = reqs.get("max_loan_amount")
        if program_max is not None:
            max_loan = min(max_loan, program_max)

        # Calculate down payment and purchase price
        min_down_pct = reqs["min_down_payment_pct"] / 100

        if float(down_payment) > 0 and purchase_price is not None and float(purchase_price) > 0:
            # Use provided values
            actual_down_pct = float(down_payment) / float(purchase_price)
            loan_amount = float(purchase_price) - float(down_payment)

            if actual_down_pct < min_down_pct:
                result["disqualifying_reasons"].append(
                    f"Down payment {actual_down_pct*100:.1f}% below minimum {min_down_pct*100:.1f}%"
                )

            ltv = (loan_amount / float(purchase_price)) * 100
            if ltv > reqs["max_ltv"]:
                result["disqualifying_reasons"].append(
                    f"LTV {ltv:.1f}% exceeds maximum {reqs['max_ltv']}%"
                )

            result["down_payment_pct"] = actual_down_pct * 100
            result["ltv"] = ltv
            max_purchase = float(purchase_price)
        else:
            # Calculate max purchase from max loan and min down payment
            # loan = purchase * (1 - down_pct)
            # purchase = loan / (1 - down_pct)
            max_purchase = max_loan / (1 - min_down_pct)
            loan_amount = max_loan
            result["down_payment_pct"] = min_down_pct * 100
            result["ltv"] = (1 - min_down_pct) * 100

        # Calculate actual monthly payment for max loan
        if monthly_rate > 0:
            pi_payment = loan_amount * factor
        else:
            pi_payment = loan_amount / n

        # Add taxes and insurance
        monthly_tax = max_purchase * self.property_tax_rate
        monthly_insurance = max_purchase * self.insurance_rate
        total_payment = pi_payment + monthly_tax + monthly_insurance

        # Add PMI/MIP if applicable
        if result["ltv"] > 80 and program == LoanProgram.CONVENTIONAL:
            total_payment += loan_amount * 0.005 / 12  # Rough PMI estimate
        elif program == LoanProgram.FHA:
            total_payment += loan_amount * reqs.get("mip_annual_pct", 0.85) / 100 / 12

        # Calculate DTI ratios
        front_end_dti = (total_payment / monthly_income) * 100
        back_end_dti = ((total_payment + monthly_debt) / monthly_income) * 100

        result["max_loan_amount"] = round(loan_amount, 2)
        result["max_purchase_price"] = round(max_purchase, 2)
        result["monthly_payment"] = round(total_payment, 2)
        result["front_end_dti"] = round(front_end_dti, 1)
        result["back_end_dti"] = round(back_end_dti, 1)

        # Final qualification check
        if not result["disqualifying_reasons"]:
            if back_end_dti <= reqs["max_dti"]:
                result["qualified"] = True
            else:
                result["conditionally_qualified"] = True
                result["disqualifying_reasons"].append(
                    f"DTI {back_end_dti:.1f}% exceeds guideline {reqs['max_dti']}%"
                )

        return result

    def _select_best_program(
        self,
        qualified: List[LoanProgram],
        preferred: Optional[LoanProgram],
    ) -> LoanProgram:
        """Select best loan program from qualified options."""
        if preferred and preferred in qualified:
            return preferred

        # Priority: Conventional > FHA > VA > USDA > Jumbo
        priority = [
            LoanProgram.CONVENTIONAL,
            LoanProgram.FHA,
            LoanProgram.VA,
            LoanProgram.USDA,
            LoanProgram.JUMBO,
        ]

        for program in priority:
            if program in qualified:
                return program

        return qualified[0]

    def _generate_recommendations(
        self,
        result: PreQualificationResult,
        program_results: Dict[LoanProgram, Dict],
        credit_score: Optional[int],
        income: IncomeBreakdown,
        debts: DebtBreakdown,
        assets: Decimal,
    ) -> List[str]:
        """Generate recommendations based on qualification results."""
        recommendations = []

        # Credit recommendations
        if credit_score is not None:
            if credit_score < 620:
                recommendations.append(
                    "Consider credit improvement before applying - "
                    "paying down credit cards and correcting errors can help"
                )
            elif credit_score < 740:
                recommendations.append(
                    f"Credit score of {credit_score} qualifies for most programs; "
                    "improving to 740+ could get better rates"
                )
        else:
            recommendations.append("Provide credit score estimate for more accurate pre-qualification")

        # DTI recommendations
        if result.back_end_dti > 43:
            recommendations.append(
                f"DTI of {result.back_end_dti:.1f}% is high - "
                "consider paying down debts or increasing income documentation"
            )

        # Down payment recommendations
        if result.down_payment_pct < 20:
            recommendations.append(
                "Less than 20% down payment will require mortgage insurance - "
                "consider saving more or using gift funds"
            )

        # Asset recommendations
        if result.months_reserves < 2:
            recommendations.append(
                "Consider building reserves of 2+ months of payments for stronger application"
            )

        # Program-specific recommendations
        if LoanProgram.VA not in result.qualified_programs:
            if not any("VA" in r.get("disqualifying_reasons", []) for r in program_results.values()):
                recommendations.append(
                    "If you're a veteran, VA loans offer 0% down payment option"
                )

        if LoanProgram.FHA in result.qualified_programs and LoanProgram.CONVENTIONAL in result.qualified_programs:
            recommendations.append(
                "Conventional loan may be better than FHA if credit is good - "
                "avoids permanent mortgage insurance"
            )

        return recommendations


# =============================================================================
# Factory
# =============================================================================

def create_prequal_calculator() -> PreQualificationCalculator:
    """Create pre-qualification calculator instance."""
    return PreQualificationCalculator()
