"""
DTI (Debt-to-Income) Optimizer Service

Calculates DTI ratios per agency guidelines and generates optimization
recommendations to help borrowers qualify for mortgage products.

Covers:
    - Front-end ratio (housing expense / gross income)
    - Back-end ratio (total obligations / gross income)
    - Agency-specific limits (Conventional, FHA, VA, USDA, Non-QM)
    - What-if scenario modeling
    - Compensating factor analysis
    - VA residual income calculation
    - Income optimization strategies

Integrates with:
    - loans table (PITIA components, rate, term, amount)
    - income_calculations / income_sources for qualifying income
    - smart_documents for credit-report debt extraction
    - leads table (co-borrower info, credit score)

Usage:
    from services.smart_docs.income.dti_optimizer_service import (
        DTIOptimizerService,
        get_dti_optimizer_service,
    )

    service = get_dti_optimizer_service(db)
    result = await service.calculate_dti(org_id=1, loan_id=42)
    scenarios = await service.optimize_dti(org_id=1, loan_id=42)
"""

import logging
import math
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from typing import Optional, Dict, List, Tuple, Any
from dataclasses import dataclass, field
from enum import Enum

from sqlalchemy.orm import Session
from sqlalchemy import text

logger = logging.getLogger(__name__)


# =============================================================================
# CONSTANTS
# =============================================================================

ZERO = Decimal("0.00")
TWO_PLACES = Decimal("0.01")
FOUR_PLACES = Decimal("0.0001")
PCT = Decimal("100")

# Minimum payment fallback: 1% of outstanding balance for revolving accounts
REVOLVING_MIN_PAYMENT_PCT = Decimal("0.01")

# Months-remaining threshold: debts with fewer months can be excluded from DTI
MONTHS_REMAINING_EXCLUDE_THRESHOLD = 10


# =============================================================================
# AGENCY DTI LIMITS
# =============================================================================

class LoanProgram(str, Enum):
    CONVENTIONAL = "conventional"
    FHA = "fha"
    VA = "va"
    USDA = "usda"
    NON_QM = "non_qm"
    JUMBO = "jumbo"


@dataclass(frozen=True)
class AgencyDTILimit:
    """DTI limits for a specific loan program."""
    program: LoanProgram
    front_end_max: Optional[Decimal]       # None = no limit (VA)
    back_end_max: Decimal
    back_end_max_with_compensating: Optional[Decimal]
    front_end_max_with_compensating: Optional[Decimal]
    notes: str


AGENCY_LIMITS: Dict[LoanProgram, AgencyDTILimit] = {
    LoanProgram.CONVENTIONAL: AgencyDTILimit(
        program=LoanProgram.CONVENTIONAL,
        front_end_max=None,  # Conventional has no explicit front-end limit
        back_end_max=Decimal("45.00"),
        back_end_max_with_compensating=Decimal("50.00"),
        front_end_max_with_compensating=None,
        notes="DU approval required for >45%. Compensating factors: reserves, "
              "minimal payment increase, strong credit, low LTV.",
    ),
    LoanProgram.FHA: AgencyDTILimit(
        program=LoanProgram.FHA,
        front_end_max=Decimal("31.00"),
        back_end_max=Decimal("43.00"),
        back_end_max_with_compensating=Decimal("57.00"),
        front_end_max_with_compensating=Decimal("43.00"),
        notes="FHA TOTAL Scorecard may approve up to 57% back-end with "
              "compensating factors. Manual UW: 31/43 hard caps unless "
              "energy-efficient or significant reserves.",
    ),
    LoanProgram.VA: AgencyDTILimit(
        program=LoanProgram.VA,
        front_end_max=None,  # VA has no front-end limit
        back_end_max=Decimal("41.00"),
        back_end_max_with_compensating=None,  # VA relies on residual income
        front_end_max_with_compensating=None,
        notes="VA does not enforce a hard front-end limit. Back-end 41% is "
              "a guideline; residual income is the primary qualifier. Loans "
              "exceeding 41% require residual income to be 120% of guideline.",
    ),
    LoanProgram.USDA: AgencyDTILimit(
        program=LoanProgram.USDA,
        front_end_max=Decimal("29.00"),
        back_end_max=Decimal("41.00"),
        back_end_max_with_compensating=Decimal("44.00"),
        front_end_max_with_compensating=Decimal("32.00"),
        notes="GUS approval may allow up to 29/41. With compensating factors, "
              "32/44 possible. Credit score 680+ preferred for exceptions.",
    ),
    LoanProgram.NON_QM: AgencyDTILimit(
        program=LoanProgram.NON_QM,
        front_end_max=None,
        back_end_max=Decimal("50.00"),
        back_end_max_with_compensating=Decimal("55.00"),
        front_end_max_with_compensating=None,
        notes="Non-QM DTI limits vary by investor. Common caps: 50% standard, "
              "55% with strong compensating factors. Some investors allow higher "
              "with significant reserves and lower LTV.",
    ),
    LoanProgram.JUMBO: AgencyDTILimit(
        program=LoanProgram.JUMBO,
        front_end_max=None,
        back_end_max=Decimal("43.00"),
        back_end_max_with_compensating=Decimal("45.00"),
        front_end_max_with_compensating=None,
        notes="Jumbo DTI limits are investor-specific. Most require 43% or "
              "lower. Strong reserves (12+ months) and high credit (720+) "
              "may allow up to 45%.",
    ),
}

# VA residual income guidelines by region and family size (monthly, in dollars)
# Regions: northeast, midwest, south, west
# Family sizes: 1, 2, 3, 4, 5 (5 = 5 or more, add $75 per additional)
VA_RESIDUAL_INCOME_TABLE: Dict[str, Dict[int, int]] = {
    "northeast": {1: 450, 2: 755, 3: 909, 4: 1025, 5: 1062},
    "midwest":   {1: 441, 2: 738, 3: 889, 4: 1003, 5: 1039},
    "south":     {1: 441, 2: 738, 3: 889, 4: 1003, 5: 1039},
    "west":      {1: 491, 2: 823, 3: 990, 4: 1117, 5: 1158},
}

# VA loan amount threshold: above this, residual requirements increase by 5%
VA_LARGE_LOAN_THRESHOLD = Decimal("80000.00")

# State-to-region mapping for VA residual income
STATE_REGION_MAP: Dict[str, str] = {
    # Northeast
    "CT": "northeast", "ME": "northeast", "MA": "northeast", "NH": "northeast",
    "NJ": "northeast", "NY": "northeast", "PA": "northeast", "RI": "northeast",
    "VT": "northeast",
    # Midwest
    "IL": "midwest", "IN": "midwest", "IA": "midwest", "KS": "midwest",
    "MI": "midwest", "MN": "midwest", "MO": "midwest", "NE": "midwest",
    "ND": "midwest", "OH": "midwest", "SD": "midwest", "WI": "midwest",
    # South
    "AL": "south", "AR": "south", "DC": "south", "DE": "south",
    "FL": "south", "GA": "south", "KY": "south", "LA": "south",
    "MD": "south", "MS": "south", "NC": "south", "OK": "south",
    "PR": "south", "SC": "south", "TN": "south", "TX": "south",
    "VA": "south", "VI": "south", "WV": "south",
    # West
    "AK": "west", "AZ": "west", "CA": "west", "CO": "west",
    "GU": "west", "HI": "west", "ID": "west", "MT": "west",
    "NM": "west", "NV": "west", "OR": "west", "UT": "west",
    "WA": "west", "WY": "west",
}


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class PITIABreakdown:
    """Principal, Interest, Taxes, Insurance, and Assessments."""
    principal_and_interest: Decimal = ZERO
    property_tax: Decimal = ZERO
    hazard_insurance: Decimal = ZERO
    mortgage_insurance: Decimal = ZERO
    hoa: Decimal = ZERO
    special_assessments: Decimal = ZERO
    flood_insurance: Decimal = ZERO
    total: Decimal = ZERO

    def recalculate_total(self) -> None:
        self.total = (
            self.principal_and_interest
            + self.property_tax
            + self.hazard_insurance
            + self.mortgage_insurance
            + self.hoa
            + self.special_assessments
            + self.flood_insurance
        ).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


@dataclass
class DebtItem:
    """A single monthly obligation from the credit report or manual entry."""
    creditor: str
    account_type: str  # installment, revolving, mortgage, child_support, alimony, contingent
    monthly_payment: Decimal
    balance: Decimal
    months_remaining: Optional[int]
    is_co_signed: bool = False
    can_be_excluded: bool = False
    exclusion_reason: Optional[str] = None
    payoff_amount: Optional[Decimal] = None


@dataclass
class IncomeSource:
    """An income source contributing to qualifying income."""
    source_type: str  # w2, self_employment, retirement, rental, asset_depletion, etc.
    description: str
    gross_monthly: Decimal
    is_taxable: bool = True
    gross_up_eligible: bool = False
    grossed_up_monthly: Optional[Decimal] = None
    documentation_status: str = "verified"  # verified, needs_docs, estimated


@dataclass
class DTIResult:
    """Complete DTI calculation result."""
    loan_id: int
    org_id: int
    pitia: PITIABreakdown
    gross_monthly_income: Decimal
    income_sources: List[IncomeSource]
    debts: List[DebtItem]
    total_monthly_debts: Decimal
    front_end_ratio: Optional[Decimal]
    back_end_ratio: Decimal
    loan_program: str
    agency_limits: Optional[AgencyDTILimit]
    front_end_compliant: bool
    back_end_compliant: bool
    back_end_compliant_with_compensating: bool
    calculated_at: str
    notes: List[str] = field(default_factory=list)


@dataclass
class OptimizationScenario:
    """A single DTI optimization recommendation."""
    strategy: str
    description: str
    current_dti_back: Decimal
    projected_dti_back: Decimal
    dti_reduction: Decimal
    current_dti_front: Optional[Decimal]
    projected_dti_front: Optional[Decimal]
    monthly_payment_impact: Decimal  # Negative = savings
    cost_to_implement: Optional[Decimal]  # One-time cost (e.g., payoff amount)
    feasibility: str  # high, medium, low
    priority: int  # 1 = highest
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CompensatingFactor:
    """A compensating factor that may allow higher DTI."""
    factor_type: str
    description: str
    strength: str  # strong, moderate, weak
    value: Optional[str] = None
    meets_threshold: bool = False


@dataclass
class ComplianceResult:
    """Result of checking DTI against agency limits."""
    loan_program: LoanProgram
    limits: AgencyDTILimit
    front_end_ratio: Optional[Decimal]
    back_end_ratio: Decimal
    front_end_pass: bool
    back_end_pass: bool
    back_end_pass_with_compensating: bool
    compensating_factors: List[CompensatingFactor]
    eligible: bool
    notes: List[str] = field(default_factory=list)


@dataclass
class ResidualResult:
    """VA residual income calculation result."""
    gross_monthly_income: Decimal
    total_deductions: Decimal
    net_effective_income: Decimal
    pitia: Decimal
    total_debts: Decimal
    estimated_maintenance: Decimal
    residual_income: Decimal
    required_residual: Decimal
    region: str
    family_size: int
    meets_requirement: bool
    surplus_or_deficit: Decimal
    notes: List[str] = field(default_factory=list)


# =============================================================================
# SERVICE
# =============================================================================

class DTIOptimizerService:
    """
    Calculates DTI ratios per agency guidelines and generates optimization
    recommendations for mortgage borrowers.

    All public methods are async and enforce org_id tenant isolation on every
    database query.
    """

    def __init__(self, db: Session):
        self.db = db

    # =========================================================================
    # 1. MAIN DTI CALCULATION
    # =========================================================================

    async def calculate_dti(
        self,
        org_id: int,
        loan_id: int,
    ) -> DTIResult:
        """
        Calculate front-end and back-end DTI ratios for a loan.

        Front-end = PITIA / Gross Monthly Income
        Back-end  = (PITIA + All Monthly Debts) / Gross Monthly Income

        PITIA = Principal + Interest + Taxes + Insurance + HOA + MI + Special Assessments.

        Args:
            org_id: Organization ID for tenant isolation.
            loan_id: Loan to calculate DTI for.

        Returns:
            DTIResult with complete breakdown.

        Raises:
            ValueError: If loan not found or not owned by org.
        """
        loan = await self._get_loan(org_id, loan_id)
        if not loan:
            raise ValueError(f"Loan {loan_id} not found in org {org_id}")

        # Build PITIA
        pitia = await self._build_pitia(loan)

        # Gather income
        income_sources = await self._gather_income(org_id, loan_id)
        gross_monthly = sum(
            (s.gross_monthly for s in income_sources), ZERO
        ).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)

        # Gather debts
        debts = await self._gather_debts(org_id, loan_id)
        total_monthly_debts = sum(
            (d.monthly_payment for d in debts if not d.can_be_excluded), ZERO
        ).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)

        # Calculate ratios
        front_end_ratio: Optional[Decimal] = None
        back_end_ratio = ZERO

        if gross_monthly > ZERO:
            front_end_ratio = (
                pitia.total / gross_monthly * PCT
            ).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)

            back_end_ratio = (
                (pitia.total + total_monthly_debts) / gross_monthly * PCT
            ).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)

        # Determine loan program
        program_str = (loan.get("loan_type") or "conventional").lower()
        program = self._normalize_program(program_str)
        limits = AGENCY_LIMITS.get(program)

        # Check compliance
        front_ok = True
        back_ok = True
        back_ok_comp = True

        if limits:
            if limits.front_end_max is not None and front_end_ratio is not None:
                front_ok = front_end_ratio <= limits.front_end_max
            if limits.back_end_max is not None:
                back_ok = back_end_ratio <= limits.back_end_max
            if limits.back_end_max_with_compensating is not None:
                back_ok_comp = back_end_ratio <= limits.back_end_max_with_compensating
            else:
                back_ok_comp = back_ok

        notes: List[str] = []
        if gross_monthly <= ZERO:
            notes.append("No qualifying income found. Upload income documents "
                         "to calculate DTI.")
        if pitia.total <= ZERO:
            notes.append("Housing payment (PITIA) is zero. Verify proposed "
                         "monthly payment, taxes, insurance, and HOA on the loan.")

        return DTIResult(
            loan_id=loan_id,
            org_id=org_id,
            pitia=pitia,
            gross_monthly_income=gross_monthly,
            income_sources=income_sources,
            debts=debts,
            total_monthly_debts=total_monthly_debts,
            front_end_ratio=front_end_ratio,
            back_end_ratio=back_end_ratio,
            loan_program=program_str,
            agency_limits=limits,
            front_end_compliant=front_ok,
            back_end_compliant=back_ok,
            back_end_compliant_with_compensating=back_ok_comp,
            calculated_at=datetime.now(timezone.utc).isoformat(),
            notes=notes,
        )

    # =========================================================================
    # 2. DTI OPTIMIZATION
    # =========================================================================

    async def optimize_dti(
        self,
        org_id: int,
        loan_id: int,
    ) -> List[OptimizationScenario]:
        """
        Analyze the loan and generate ranked DTI optimization recommendations.

        Strategies evaluated:
            - Pay off debts with < 10 months remaining
            - Pay down revolving balances
            - Add co-borrower income
            - Use asset depletion income
            - Gross up non-taxable income
            - Remove contingent liabilities
            - Subordinate debts
            - Rate reduction impact

        Args:
            org_id: Organization ID for tenant isolation.
            loan_id: Loan to optimize.

        Returns:
            List of OptimizationScenario sorted by priority (highest impact first).
        """
        dti = await self.calculate_dti(org_id, loan_id)
        scenarios: List[OptimizationScenario] = []

        if dti.gross_monthly_income <= ZERO:
            return scenarios

        current_back = dti.back_end_ratio
        current_front = dti.front_end_ratio
        total_housing = dti.pitia.total
        income = dti.gross_monthly_income

        # --- Strategy 1: Pay off debts with < 10 months remaining ---
        excludable_debts = [
            d for d in dti.debts
            if d.months_remaining is not None
            and d.months_remaining <= MONTHS_REMAINING_EXCLUDE_THRESHOLD
            and not d.can_be_excluded
            and d.account_type == "installment"
        ]
        for debt in excludable_debts:
            new_total_debts = dti.total_monthly_debts - debt.monthly_payment
            new_back = (
                (total_housing + new_total_debts) / income * PCT
            ).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
            reduction = current_back - new_back

            if reduction > ZERO:
                scenarios.append(OptimizationScenario(
                    strategy="exclude_short_term_debt",
                    description=(
                        f"Exclude {debt.creditor} ({debt.months_remaining} months "
                        f"remaining, {_fmt_currency(debt.monthly_payment)}/mo). "
                        f"Debts with <10 months remaining can be excluded from DTI "
                        f"per agency guidelines."
                    ),
                    current_dti_back=current_back,
                    projected_dti_back=new_back,
                    dti_reduction=reduction,
                    current_dti_front=current_front,
                    projected_dti_front=current_front,  # Housing unchanged
                    monthly_payment_impact=-debt.monthly_payment,
                    cost_to_implement=debt.payoff_amount,
                    feasibility="high",
                    priority=1,
                    details={
                        "creditor": debt.creditor,
                        "months_remaining": debt.months_remaining,
                        "payoff_amount": str(debt.payoff_amount) if debt.payoff_amount else None,
                    },
                ))

        # --- Strategy 2: Pay down revolving debt ---
        revolving_debts = [
            d for d in dti.debts
            if d.account_type == "revolving"
            and d.monthly_payment > ZERO
            and d.balance > ZERO
        ]
        for debt in revolving_debts:
            # Scenario: pay off entirely
            new_total_debts = dti.total_monthly_debts - debt.monthly_payment
            new_back = (
                (total_housing + new_total_debts) / income * PCT
            ).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
            reduction = current_back - new_back

            if reduction > ZERO:
                scenarios.append(OptimizationScenario(
                    strategy="payoff_revolving",
                    description=(
                        f"Pay off {debt.creditor} revolving balance "
                        f"({_fmt_currency(debt.balance)}). Eliminates "
                        f"{_fmt_currency(debt.monthly_payment)}/mo from DTI."
                    ),
                    current_dti_back=current_back,
                    projected_dti_back=new_back,
                    dti_reduction=reduction,
                    current_dti_front=current_front,
                    projected_dti_front=current_front,
                    monthly_payment_impact=-debt.monthly_payment,
                    cost_to_implement=debt.balance,
                    feasibility="medium",
                    priority=2,
                    details={
                        "creditor": debt.creditor,
                        "balance": str(debt.balance),
                        "current_payment": str(debt.monthly_payment),
                    },
                ))

            # Scenario: pay down 50% (reduces minimum payment roughly proportionally)
            if debt.balance > Decimal("500"):
                half_balance = (debt.balance / 2).quantize(TWO_PLACES)
                reduced_payment = (half_balance * REVOLVING_MIN_PAYMENT_PCT).quantize(
                    TWO_PLACES, rounding=ROUND_HALF_UP
                )
                # Use whichever is greater: calculated min or $25
                reduced_payment = max(reduced_payment, Decimal("25.00"))
                payment_savings = debt.monthly_payment - reduced_payment
                if payment_savings > ZERO:
                    new_total_debts_half = dti.total_monthly_debts - payment_savings
                    new_back_half = (
                        (total_housing + new_total_debts_half) / income * PCT
                    ).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
                    reduction_half = current_back - new_back_half

                    if reduction_half > ZERO:
                        scenarios.append(OptimizationScenario(
                            strategy="paydown_revolving_50pct",
                            description=(
                                f"Pay down {debt.creditor} by 50% "
                                f"({_fmt_currency(half_balance)}). Reduces minimum "
                                f"payment from {_fmt_currency(debt.monthly_payment)} "
                                f"to ~{_fmt_currency(reduced_payment)}/mo."
                            ),
                            current_dti_back=current_back,
                            projected_dti_back=new_back_half,
                            dti_reduction=reduction_half,
                            current_dti_front=current_front,
                            projected_dti_front=current_front,
                            monthly_payment_impact=-payment_savings,
                            cost_to_implement=half_balance,
                            feasibility="medium",
                            priority=3,
                            details={
                                "creditor": debt.creditor,
                                "paydown_amount": str(half_balance),
                                "new_payment": str(reduced_payment),
                            },
                        ))

        # --- Strategy 3: Add co-borrower income ---
        coborrower_income = await self._estimate_coborrower_income(org_id, loan_id)
        if coborrower_income and coborrower_income > ZERO:
            new_income = income + coborrower_income
            new_front = (
                total_housing / new_income * PCT
            ).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
            new_back_cob = (
                (total_housing + dti.total_monthly_debts) / new_income * PCT
            ).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
            reduction = current_back - new_back_cob

            if reduction > ZERO:
                scenarios.append(OptimizationScenario(
                    strategy="add_coborrower",
                    description=(
                        f"Add co-borrower income ({_fmt_currency(coborrower_income)}/mo). "
                        f"DTI drops from {current_back}% to {new_back_cob}%."
                    ),
                    current_dti_back=current_back,
                    projected_dti_back=new_back_cob,
                    dti_reduction=reduction,
                    current_dti_front=current_front,
                    projected_dti_front=new_front,
                    monthly_payment_impact=ZERO,
                    cost_to_implement=None,
                    feasibility="medium",
                    priority=4,
                    details={
                        "coborrower_monthly_income": str(coborrower_income),
                        "note": "Co-borrower debts will also be included. "
                                "Net impact depends on co-borrower obligations.",
                    },
                ))

        # --- Strategy 4: Gross up non-taxable income ---
        grossable = [
            s for s in dti.income_sources
            if s.gross_up_eligible and not s.is_taxable
        ]
        if grossable:
            gross_up_factor = Decimal("1.25")  # 25% gross-up for non-taxable
            additional_income = sum(
                (s.gross_monthly * (gross_up_factor - Decimal("1.00")) for s in grossable),
                ZERO,
            ).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
            new_income_gu = income + additional_income
            new_front_gu = (
                total_housing / new_income_gu * PCT
            ).quantize(TWO_PLACES, rounding=ROUND_HALF_UP) if new_income_gu > ZERO else None
            new_back_gu = (
                (total_housing + dti.total_monthly_debts) / new_income_gu * PCT
            ).quantize(TWO_PLACES, rounding=ROUND_HALF_UP) if new_income_gu > ZERO else current_back
            reduction_gu = current_back - new_back_gu

            if reduction_gu > ZERO:
                source_names = ", ".join(s.description for s in grossable)
                scenarios.append(OptimizationScenario(
                    strategy="gross_up_nontaxable",
                    description=(
                        f"Gross up non-taxable income by 25% ({source_names}). "
                        f"Adds {_fmt_currency(additional_income)}/mo to qualifying income."
                    ),
                    current_dti_back=current_back,
                    projected_dti_back=new_back_gu,
                    dti_reduction=reduction_gu,
                    current_dti_front=current_front,
                    projected_dti_front=new_front_gu,
                    monthly_payment_impact=ZERO,
                    cost_to_implement=None,
                    feasibility="high",
                    priority=2,
                    details={
                        "gross_up_factor": "1.25",
                        "additional_monthly": str(additional_income),
                        "sources": source_names,
                    },
                ))

        # --- Strategy 5: Remove contingent liabilities ---
        contingent = [
            d for d in dti.debts
            if d.is_co_signed and not d.can_be_excluded
        ]
        for debt in contingent:
            new_total_cont = dti.total_monthly_debts - debt.monthly_payment
            new_back_cont = (
                (total_housing + new_total_cont) / income * PCT
            ).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
            reduction_cont = current_back - new_back_cont

            if reduction_cont > ZERO:
                scenarios.append(OptimizationScenario(
                    strategy="remove_contingent_liability",
                    description=(
                        f"Remove contingent liability: {debt.creditor} "
                        f"({_fmt_currency(debt.monthly_payment)}/mo). "
                        f"Provide 12 months of payment history showing the primary "
                        f"borrower has been making payments."
                    ),
                    current_dti_back=current_back,
                    projected_dti_back=new_back_cont,
                    dti_reduction=reduction_cont,
                    current_dti_front=current_front,
                    projected_dti_front=current_front,
                    monthly_payment_impact=-debt.monthly_payment,
                    cost_to_implement=None,
                    feasibility="medium",
                    priority=3,
                    details={
                        "creditor": debt.creditor,
                        "payment": str(debt.monthly_payment),
                        "documentation_needed": "12 months cancelled checks or "
                                                 "bank statements from primary borrower",
                    },
                ))

        # --- Strategy 6: Asset depletion income ---
        asset_income = await self._estimate_asset_depletion_income(org_id, loan_id)
        if asset_income and asset_income > ZERO:
            new_income_ad = income + asset_income
            new_back_ad = (
                (total_housing + dti.total_monthly_debts) / new_income_ad * PCT
            ).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
            new_front_ad = (
                total_housing / new_income_ad * PCT
            ).quantize(TWO_PLACES, rounding=ROUND_HALF_UP) if new_income_ad > ZERO else None
            reduction_ad = current_back - new_back_ad

            if reduction_ad > ZERO:
                scenarios.append(OptimizationScenario(
                    strategy="asset_depletion",
                    description=(
                        f"Use asset depletion income ({_fmt_currency(asset_income)}/mo). "
                        f"Eligible liquid assets divided by remaining loan term in months, "
                        f"net of required reserves."
                    ),
                    current_dti_back=current_back,
                    projected_dti_back=new_back_ad,
                    dti_reduction=reduction_ad,
                    current_dti_front=current_front,
                    projected_dti_front=new_front_ad,
                    monthly_payment_impact=ZERO,
                    cost_to_implement=None,
                    feasibility="medium",
                    priority=5,
                    details={
                        "monthly_asset_income": str(asset_income),
                        "note": "Requires verification of liquid asset accounts. "
                                "Retirement accounts typically counted at 60-70% of value.",
                    },
                ))

        # --- Strategy 7: Rate reduction scenario ---
        loan_data = await self._get_loan(org_id, loan_id)
        if loan_data:
            current_rate = _to_decimal(loan_data.get("rate"))
            loan_amount = _to_decimal(loan_data.get("amount"))
            term = loan_data.get("term") or 360

            if current_rate and current_rate > ZERO and loan_amount and loan_amount > ZERO:
                for rate_drop in [Decimal("0.25"), Decimal("0.50"), Decimal("1.00")]:
                    new_rate = current_rate - rate_drop
                    if new_rate <= ZERO:
                        continue

                    new_pi = _calculate_monthly_pi(loan_amount, new_rate, term)
                    current_pi = dti.pitia.principal_and_interest
                    pi_savings = current_pi - new_pi

                    if pi_savings > ZERO:
                        new_pitia = dti.pitia.total - pi_savings
                        new_back_rate = (
                            (new_pitia + dti.total_monthly_debts) / income * PCT
                        ).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
                        new_front_rate = (
                            new_pitia / income * PCT
                        ).quantize(TWO_PLACES, rounding=ROUND_HALF_UP) if income > ZERO else None
                        reduction_rate = current_back - new_back_rate

                        if reduction_rate > ZERO:
                            scenarios.append(OptimizationScenario(
                                strategy="rate_reduction",
                                description=(
                                    f"If rate drops {rate_drop}% "
                                    f"(from {current_rate}% to {new_rate}%), "
                                    f"P&I drops by {_fmt_currency(pi_savings)}/mo. "
                                    f"DTI: {current_back}% -> {new_back_rate}%."
                                ),
                                current_dti_back=current_back,
                                projected_dti_back=new_back_rate,
                                dti_reduction=reduction_rate,
                                current_dti_front=current_front,
                                projected_dti_front=new_front_rate,
                                monthly_payment_impact=-pi_savings,
                                cost_to_implement=None,
                                feasibility="low",
                                priority=6,
                                details={
                                    "current_rate": str(current_rate),
                                    "new_rate": str(new_rate),
                                    "rate_drop": str(rate_drop),
                                    "pi_savings": str(pi_savings),
                                },
                            ))

        # Sort by DTI reduction descending, then priority ascending
        scenarios.sort(key=lambda s: (-s.dti_reduction, s.priority))

        # Re-number priorities based on sorted order
        for idx, scenario in enumerate(scenarios, start=1):
            scenario.priority = idx

        return scenarios

    # =========================================================================
    # 3. WHAT-IF SCENARIO
    # =========================================================================

    async def run_what_if(
        self,
        org_id: int,
        loan_id: int,
        changes: Dict[str, Any],
    ) -> DTIResult:
        """
        Run a what-if DTI calculation with hypothetical changes.

        Supported change keys:
            - remove_debt_ids: List[int]       -- debt item indices to remove
            - add_monthly_income: Decimal      -- additional monthly income
            - new_rate: Decimal                -- new interest rate
            - payoff_debts: List[Dict]         -- [{"creditor": str, "amount": Decimal}]
            - additional_coborrower_income: Decimal
            - gross_up_nontaxable: bool        -- apply 25% gross-up

        Args:
            org_id: Organization ID for tenant isolation.
            loan_id: Loan to run scenario on.
            changes: Dict of hypothetical changes.

        Returns:
            DTIResult reflecting the what-if scenario.
        """
        # Start from current state
        dti = await self.calculate_dti(org_id, loan_id)

        income = dti.gross_monthly_income
        debts = list(dti.debts)
        pitia = dti.pitia

        # Apply income changes
        if changes.get("add_monthly_income"):
            additional = _to_decimal(changes["add_monthly_income"])
            income = income + additional

        if changes.get("additional_coborrower_income"):
            cob_income = _to_decimal(changes["additional_coborrower_income"])
            income = income + cob_income
            dti.income_sources.append(IncomeSource(
                source_type="coborrower",
                description="Co-borrower income (what-if)",
                gross_monthly=cob_income,
                is_taxable=True,
            ))

        if changes.get("gross_up_nontaxable"):
            gross_up_factor = Decimal("1.25")
            for source in dti.income_sources:
                if source.gross_up_eligible and not source.is_taxable:
                    additional = source.gross_monthly * (gross_up_factor - Decimal("1"))
                    income = income + additional
                    source.grossed_up_monthly = (
                        source.gross_monthly * gross_up_factor
                    ).quantize(TWO_PLACES)

        # Apply debt removals
        remove_indices = set(changes.get("remove_debt_ids", []))
        if remove_indices:
            debts = [d for i, d in enumerate(debts) if i not in remove_indices]

        # Apply debt payoffs by creditor name
        payoffs = changes.get("payoff_debts", [])
        for payoff in payoffs:
            creditor = payoff.get("creditor", "").lower()
            debts = [
                d for d in debts
                if d.creditor.lower() != creditor
            ]

        # Apply rate change
        if changes.get("new_rate") is not None:
            new_rate = _to_decimal(changes["new_rate"])
            loan_data = await self._get_loan(org_id, loan_id)
            if loan_data:
                loan_amount = _to_decimal(loan_data.get("amount"))
                term = loan_data.get("term") or 360
                if loan_amount and loan_amount > ZERO and new_rate > ZERO:
                    new_pi = _calculate_monthly_pi(loan_amount, new_rate, term)
                    pitia = PITIABreakdown(
                        principal_and_interest=new_pi,
                        property_tax=pitia.property_tax,
                        hazard_insurance=pitia.hazard_insurance,
                        mortgage_insurance=pitia.mortgage_insurance,
                        hoa=pitia.hoa,
                        special_assessments=pitia.special_assessments,
                        flood_insurance=pitia.flood_insurance,
                    )
                    pitia.recalculate_total()

        # Recalculate
        total_monthly_debts = sum(
            (d.monthly_payment for d in debts if not d.can_be_excluded), ZERO
        ).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)

        front_end: Optional[Decimal] = None
        back_end = ZERO
        if income > ZERO:
            front_end = (
                pitia.total / income * PCT
            ).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
            back_end = (
                (pitia.total + total_monthly_debts) / income * PCT
            ).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)

        program = self._normalize_program(dti.loan_program)
        limits = AGENCY_LIMITS.get(program)

        front_ok = True
        back_ok = True
        back_ok_comp = True
        if limits:
            if limits.front_end_max is not None and front_end is not None:
                front_ok = front_end <= limits.front_end_max
            back_ok = back_end <= limits.back_end_max
            if limits.back_end_max_with_compensating is not None:
                back_ok_comp = back_end <= limits.back_end_max_with_compensating
            else:
                back_ok_comp = back_ok

        return DTIResult(
            loan_id=loan_id,
            org_id=org_id,
            pitia=pitia,
            gross_monthly_income=income,
            income_sources=dti.income_sources,
            debts=debts,
            total_monthly_debts=total_monthly_debts,
            front_end_ratio=front_end,
            back_end_ratio=back_end,
            loan_program=dti.loan_program,
            agency_limits=limits,
            front_end_compliant=front_ok,
            back_end_compliant=back_ok,
            back_end_compliant_with_compensating=back_ok_comp,
            calculated_at=datetime.now(timezone.utc).isoformat(),
            notes=["What-if scenario — not a binding qualification."],
        )

    # =========================================================================
    # 4. AGENCY LIMIT CHECK
    # =========================================================================

    async def check_agency_limits(
        self,
        dti_result: DTIResult,
        loan_type: str,
    ) -> ComplianceResult:
        """
        Check DTI ratios against agency-specific limits.

        Evaluates front-end and back-end ratios against the specified loan
        program's limits, both with and without compensating factors.

        Args:
            dti_result: A previously calculated DTIResult.
            loan_type: Loan program string (conventional, fha, va, usda, non_qm).

        Returns:
            ComplianceResult with pass/fail and compensating factor analysis.
        """
        program = self._normalize_program(loan_type)
        limits = AGENCY_LIMITS.get(program)

        if not limits:
            return ComplianceResult(
                loan_program=program,
                limits=AGENCY_LIMITS[LoanProgram.CONVENTIONAL],
                front_end_ratio=dti_result.front_end_ratio,
                back_end_ratio=dti_result.back_end_ratio,
                front_end_pass=True,
                back_end_pass=True,
                back_end_pass_with_compensating=True,
                compensating_factors=[],
                eligible=True,
                notes=[f"No specific limits found for '{loan_type}'. "
                       "Conventional limits applied as default."],
            )

        front_pass = True
        if limits.front_end_max is not None and dti_result.front_end_ratio is not None:
            front_pass = dti_result.front_end_ratio <= limits.front_end_max

        back_pass = dti_result.back_end_ratio <= limits.back_end_max

        # Check with compensating factors
        comp_factors = await self.get_compensating_factors(
            dti_result.org_id, dti_result.loan_id
        )

        back_pass_comp = back_pass
        if not back_pass and limits.back_end_max_with_compensating:
            back_pass_comp = dti_result.back_end_ratio <= limits.back_end_max_with_compensating

        # If relying on compensating factors, need at least 2 strong ones
        strong_factors = [f for f in comp_factors if f.meets_threshold]
        compensating_eligible = len(strong_factors) >= 2 if back_pass_comp and not back_pass else True

        eligible = front_pass and (back_pass or (back_pass_comp and compensating_eligible))

        notes: List[str] = []
        if not front_pass:
            notes.append(
                f"Front-end DTI {dti_result.front_end_ratio}% exceeds "
                f"{limits.front_end_max}% limit for {program.value}."
            )
        if not back_pass:
            if back_pass_comp and compensating_eligible:
                notes.append(
                    f"Back-end DTI {dti_result.back_end_ratio}% exceeds standard "
                    f"{limits.back_end_max}% but within {limits.back_end_max_with_compensating}% "
                    f"extended limit. {len(strong_factors)} compensating factors identified."
                )
            elif back_pass_comp and not compensating_eligible:
                notes.append(
                    f"Back-end DTI {dti_result.back_end_ratio}% within extended limit "
                    f"but insufficient compensating factors ({len(strong_factors)}/2 required)."
                )
            else:
                notes.append(
                    f"Back-end DTI {dti_result.back_end_ratio}% exceeds all limits "
                    f"for {program.value}."
                )

        if program == LoanProgram.VA:
            notes.append(
                "VA loans prioritize residual income over DTI ratios. "
                "Run calculate_residual_income for VA qualification."
            )

        notes.append(limits.notes)

        return ComplianceResult(
            loan_program=program,
            limits=limits,
            front_end_ratio=dti_result.front_end_ratio,
            back_end_ratio=dti_result.back_end_ratio,
            front_end_pass=front_pass,
            back_end_pass=back_pass,
            back_end_pass_with_compensating=back_pass_comp and compensating_eligible,
            compensating_factors=comp_factors,
            eligible=eligible,
            notes=notes,
        )

    # =========================================================================
    # 5. VA RESIDUAL INCOME CALCULATION
    # =========================================================================

    async def calculate_residual_income(
        self,
        income: Decimal,
        debts: Decimal,
        family_size: int,
        region: str,
        pitia: Optional[Decimal] = None,
        loan_amount: Optional[Decimal] = None,
        org_id: Optional[int] = None,
        loan_id: Optional[int] = None,
    ) -> ResidualResult:
        """
        Calculate VA residual income.

        Residual income = Gross monthly income - Federal/state tax estimate
                          - PITIA - all monthly debts - maintenance/utilities

        Regional minimum residual income varies by family size and geography.

        Args:
            income: Gross monthly income.
            debts: Total monthly debt obligations (excluding PITIA).
            family_size: Number of family members (1-7+).
            region: VA region (northeast, midwest, south, west) or state code.
            pitia: Monthly PITIA. If None and loan_id provided, calculated from loan.
            loan_amount: Loan amount (for large-loan threshold adjustment).
            org_id: Optional org_id for DB lookups.
            loan_id: Optional loan_id to pull PITIA from loan data.

        Returns:
            ResidualResult with pass/fail and surplus.
        """
        # Resolve region from state code if needed
        resolved_region = region.lower()
        if len(region) == 2:
            resolved_region = STATE_REGION_MAP.get(region.upper(), "south")

        if resolved_region not in VA_RESIDUAL_INCOME_TABLE:
            resolved_region = "south"  # Default

        # Get PITIA from loan if not provided
        if pitia is None and org_id is not None and loan_id is not None:
            loan_data = await self._get_loan(org_id, loan_id)
            if loan_data:
                pitia_obj = await self._build_pitia(loan_data)
                pitia = pitia_obj.total

        if pitia is None:
            pitia = ZERO

        # Federal/state tax estimate (rough: 25% effective rate for VA borrowers)
        tax_rate = Decimal("0.25")
        estimated_taxes = (income * tax_rate).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)

        # Maintenance and utilities estimate: 14 cents per sq ft
        # VA guideline: use $0.14 * home_size_sqft or a floor of ~$250/mo
        # Without actual sq ft data, use a conservative estimate
        estimated_maintenance = Decimal("250.00")

        # Net effective income
        net_income = income - estimated_taxes

        # Residual income calculation
        residual = (
            net_income - pitia - debts - estimated_maintenance
        ).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)

        # Required residual income from VA table
        family_key = min(family_size, 5)
        required = Decimal(str(
            VA_RESIDUAL_INCOME_TABLE[resolved_region].get(family_key, 1039)
        ))

        # Add $75 per additional family member above 5
        if family_size > 5:
            required += Decimal("75") * (family_size - 5)

        # Large loan adjustment: increase required by 5%
        if loan_amount and loan_amount > VA_LARGE_LOAN_THRESHOLD:
            required = (required * Decimal("1.05")).quantize(
                TWO_PLACES, rounding=ROUND_HALF_UP
            )

        meets = residual >= required
        surplus = residual - required

        notes: List[str] = []
        if not meets:
            deficit = abs(surplus)
            notes.append(
                f"Residual income shortfall of {_fmt_currency(deficit)}/mo. "
                f"Need {_fmt_currency(required)}/mo, have {_fmt_currency(residual)}/mo."
            )
        else:
            notes.append(
                f"Residual income meets VA requirement. "
                f"Surplus of {_fmt_currency(surplus)}/mo above minimum."
            )

        # If DTI > 41%, residual must be 120% of guideline
        effective_dti = ZERO
        if income > ZERO:
            effective_dti = (
                (pitia + debts) / income * PCT
            ).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)

        if effective_dti > Decimal("41"):
            elevated_required = (required * Decimal("1.20")).quantize(
                TWO_PLACES, rounding=ROUND_HALF_UP
            )
            if residual < elevated_required:
                meets = False
                notes.append(
                    f"DTI exceeds 41% ({effective_dti}%). "
                    f"VA requires 120% of residual guideline: "
                    f"{_fmt_currency(elevated_required)}/mo. "
                    f"Current residual: {_fmt_currency(residual)}/mo."
                )
                required = elevated_required
                surplus = residual - required

        return ResidualResult(
            gross_monthly_income=income,
            total_deductions=estimated_taxes,
            net_effective_income=net_income,
            pitia=pitia,
            total_debts=debts,
            estimated_maintenance=estimated_maintenance,
            residual_income=residual,
            required_residual=required,
            region=resolved_region,
            family_size=family_size,
            meets_requirement=meets,
            surplus_or_deficit=surplus,
            notes=notes,
        )

    # =========================================================================
    # 6. COMPENSATING FACTORS
    # =========================================================================

    async def get_compensating_factors(
        self,
        org_id: int,
        loan_id: int,
    ) -> List[CompensatingFactor]:
        """
        Analyze the loan file for compensating factors that may allow
        higher DTI approval.

        Evaluates:
            - Cash reserves (months of PITIA)
            - Housing payment increase (current vs proposed)
            - Credit score
            - LTV ratio
            - Down payment percentage
            - Residual income (VA)

        Args:
            org_id: Organization ID for tenant isolation.
            loan_id: Loan to analyze.

        Returns:
            List of CompensatingFactor with strength assessment.
        """
        factors: List[CompensatingFactor] = []

        loan = await self._get_loan(org_id, loan_id)
        if not loan:
            return factors

        pitia_obj = await self._build_pitia(loan)
        pitia_total = pitia_obj.total

        # --- Factor 1: Cash reserves ---
        reserves = await self._get_reserves_months(org_id, loan_id, pitia_total)
        if reserves is not None:
            if reserves >= 6:
                strength = "strong"
                meets = True
            elif reserves >= 3:
                strength = "moderate"
                meets = True
            else:
                strength = "weak"
                meets = False

            factors.append(CompensatingFactor(
                factor_type="cash_reserves",
                description=f"{reserves} months of PITIA in verified reserves",
                strength=strength,
                value=f"{reserves} months",
                meets_threshold=meets,
            ))

        # --- Factor 2: Minimal housing payment increase ---
        present_payment = _to_decimal(loan.get("present_monthly_payment"))
        proposed_payment = _to_decimal(loan.get("proposed_monthly_payment")) or pitia_total

        if present_payment and present_payment > ZERO and proposed_payment > ZERO:
            increase_pct = (
                (proposed_payment - present_payment) / present_payment * PCT
            ).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)

            if increase_pct <= Decimal("5.00"):
                strength = "strong"
                meets = True
                desc = f"Housing payment increase of {increase_pct}% (<=5%)"
            elif increase_pct <= Decimal("15.00"):
                strength = "moderate"
                meets = True
                desc = f"Housing payment increase of {increase_pct}% (<=15%)"
            elif increase_pct <= ZERO:
                strength = "strong"
                meets = True
                desc = f"Housing payment decrease of {abs(increase_pct)}%"
            else:
                strength = "weak"
                meets = False
                desc = f"Housing payment increase of {increase_pct}%"

            factors.append(CompensatingFactor(
                factor_type="payment_increase",
                description=desc,
                strength=strength,
                value=f"{increase_pct}%",
                meets_threshold=meets,
            ))

        # --- Factor 3: Credit score ---
        credit_score = await self._get_credit_score(org_id, loan_id)
        if credit_score:
            if credit_score >= 740:
                strength = "strong"
                meets = True
            elif credit_score >= 700:
                strength = "moderate"
                meets = True
            elif credit_score >= 680:
                strength = "weak"
                meets = False
            else:
                strength = "weak"
                meets = False

            factors.append(CompensatingFactor(
                factor_type="credit_score",
                description=f"Credit score: {credit_score}",
                strength=strength,
                value=str(credit_score),
                meets_threshold=meets,
            ))

        # --- Factor 4: LTV ratio ---
        ltv = _to_decimal(loan.get("ltv"))
        if ltv and ltv > ZERO:
            if ltv <= Decimal("75.00"):
                strength = "strong"
                meets = True
            elif ltv <= Decimal("80.00"):
                strength = "moderate"
                meets = True
            else:
                strength = "weak"
                meets = False

            factors.append(CompensatingFactor(
                factor_type="low_ltv",
                description=f"LTV: {ltv}%",
                strength=strength,
                value=f"{ltv}%",
                meets_threshold=meets,
            ))

        # --- Factor 5: Down payment ---
        purchase_price = _to_decimal(loan.get("purchase_price"))
        down_payment = _to_decimal(loan.get("down_payment"))
        if purchase_price and purchase_price > ZERO and down_payment and down_payment > ZERO:
            dp_pct = (
                down_payment / purchase_price * PCT
            ).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)

            if dp_pct >= Decimal("20.00"):
                strength = "strong"
                meets = True
            elif dp_pct >= Decimal("10.00"):
                strength = "moderate"
                meets = True
            else:
                strength = "weak"
                meets = False

            factors.append(CompensatingFactor(
                factor_type="down_payment",
                description=f"Down payment: {dp_pct}% ({_fmt_currency(down_payment)})",
                strength=strength,
                value=f"{dp_pct}%",
                meets_threshold=meets,
            ))

        return factors

    # =========================================================================
    # PRIVATE HELPERS
    # =========================================================================

    async def _get_loan(
        self,
        org_id: int,
        loan_id: int,
    ) -> Optional[Dict[str, Any]]:
        """Fetch loan data with tenant isolation."""
        row = self.db.execute(
            text("""
                SELECT
                    id, loan_number, loan_type, stage,
                    amount, purchase_price, down_payment,
                    rate, term,
                    monthly_payment, property_tax, hazard_insurance,
                    mortgage_insurance, hoa_amount,
                    proposed_monthly_payment, present_monthly_payment,
                    present_housing_expense, proposed_housing_expense,
                    ltv, cltv, loan_purpose, property_state,
                    coborrower_name, co_borrower_email,
                    second_loan_payment
                FROM loans
                WHERE id = :loan_id
                  AND organization_id = :org_id
            """),
            {"loan_id": loan_id, "org_id": org_id},
        ).fetchone()

        if not row:
            return None

        return dict(row._mapping) if hasattr(row, "_mapping") else {
            "id": row[0], "loan_number": row[1], "loan_type": row[2],
            "stage": row[3], "amount": row[4], "purchase_price": row[5],
            "down_payment": row[6], "rate": row[7], "term": row[8],
            "monthly_payment": row[9], "property_tax": row[10],
            "hazard_insurance": row[11], "mortgage_insurance": row[12],
            "hoa_amount": row[13], "proposed_monthly_payment": row[14],
            "present_monthly_payment": row[15], "present_housing_expense": row[16],
            "proposed_housing_expense": row[17], "ltv": row[18], "cltv": row[19],
            "loan_purpose": row[20], "property_state": row[21],
            "coborrower_name": row[22], "co_borrower_email": row[23],
            "second_loan_payment": row[24],
        }

    async def _build_pitia(self, loan: Dict[str, Any]) -> PITIABreakdown:
        """
        Build PITIA breakdown from loan data.

        If principal_and_interest is not directly stored, calculate from
        loan amount, rate, and term using the amortization formula.
        """
        rate = _to_decimal(loan.get("rate"))
        amount = _to_decimal(loan.get("amount"))
        term = loan.get("term") or 360

        # Calculate P&I
        monthly_payment_stored = _to_decimal(loan.get("monthly_payment"))
        property_tax = _to_decimal(loan.get("property_tax"))
        hazard_insurance = _to_decimal(loan.get("hazard_insurance"))
        mortgage_insurance = _to_decimal(loan.get("mortgage_insurance"))
        hoa = _to_decimal(loan.get("hoa_amount"))

        # If we have a stored monthly_payment (which is total PITIA), derive P&I
        # Otherwise calculate from rate/amount/term
        if monthly_payment_stored and monthly_payment_stored > ZERO:
            # monthly_payment on the loan is typically the total PITIA
            # Subtract known components to derive P&I
            pi = (
                monthly_payment_stored
                - property_tax
                - hazard_insurance
                - mortgage_insurance
                - hoa
            ).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
            # Ensure P&I is not negative (data quality issue)
            if pi < ZERO:
                pi = monthly_payment_stored
        elif rate and rate > ZERO and amount and amount > ZERO:
            pi = _calculate_monthly_pi(amount, rate, term)
        else:
            pi = ZERO

        second_loan = _to_decimal(loan.get("second_loan_payment"))

        pitia = PITIABreakdown(
            principal_and_interest=pi,
            property_tax=property_tax,
            hazard_insurance=hazard_insurance,
            mortgage_insurance=mortgage_insurance,
            hoa=hoa,
            special_assessments=second_loan,  # Include 2nd loan as assessment
            flood_insurance=ZERO,
        )
        pitia.recalculate_total()

        return pitia

    async def _gather_income(
        self,
        org_id: int,
        loan_id: int,
    ) -> List[IncomeSource]:
        """
        Gather qualifying income from income_calculations and income_sources tables.

        Falls back to lead-level annual_income if no income calculation exists.
        """
        sources: List[IncomeSource] = []

        # Try income_sources table first (populated by income_calculator_service)
        try:
            rows = self.db.execute(
                text("""
                    SELECT
                        is2.source_type,
                        is2.employer_name,
                        is2.total_monthly,
                        is2.base_monthly,
                        is2.overtime_monthly,
                        is2.bonus_monthly,
                        is2.commission_monthly,
                        is2.other_monthly,
                        is2.trending,
                        is2.confidence
                    FROM income_sources is2
                    JOIN income_calculations ic ON ic.id = is2.calculation_id
                    JOIN loans l ON l.id = ic.loan_id
                    WHERE ic.loan_id = :loan_id
                      AND l.organization_id = :org_id
                    ORDER BY ic.calculated_at DESC
                """),
                {"loan_id": loan_id, "org_id": org_id},
            ).fetchall()

            for row in rows:
                mapping = dict(row._mapping) if hasattr(row, "_mapping") else {}
                source_type = mapping.get("source_type", "unknown")
                total_monthly = _to_decimal(mapping.get("total_monthly"))

                is_taxable = source_type not in (
                    "VA_DISABILITY", "SOCIAL_SECURITY", "CHILD_SUPPORT_RECEIVED",
                )
                gross_up_eligible = not is_taxable

                sources.append(IncomeSource(
                    source_type=source_type,
                    description=mapping.get("employer_name") or source_type,
                    gross_monthly=total_monthly,
                    is_taxable=is_taxable,
                    gross_up_eligible=gross_up_eligible,
                    documentation_status="verified",
                ))

        except Exception as e:
            logger.warning(
                f"Failed to query income_sources for loan {loan_id}: {e}"
            )

        # Fallback: lead-level annual_income
        if not sources:
            try:
                lead_row = self.db.execute(
                    text("""
                        SELECT ld.annual_income
                        FROM leads ld
                        JOIN loans l ON l.loan_number = ld.loan_number
                        WHERE l.id = :loan_id
                          AND l.organization_id = :org_id
                          AND ld.annual_income IS NOT NULL
                          AND ld.annual_income > 0
                        LIMIT 1
                    """),
                    {"loan_id": loan_id, "org_id": org_id},
                ).fetchone()

                if lead_row:
                    annual = _to_decimal(
                        lead_row._mapping.get("annual_income")
                        if hasattr(lead_row, "_mapping")
                        else lead_row[0]
                    )
                    if annual and annual > ZERO:
                        monthly = (annual / 12).quantize(
                            TWO_PLACES, rounding=ROUND_HALF_UP
                        )
                        sources.append(IncomeSource(
                            source_type="stated_annual",
                            description="Annual income from application",
                            gross_monthly=monthly,
                            is_taxable=True,
                            documentation_status="estimated",
                        ))
            except Exception as e:
                logger.warning(
                    f"Failed to query lead income for loan {loan_id}: {e}"
                )

        return sources

    async def _gather_debts(
        self,
        org_id: int,
        loan_id: int,
    ) -> List[DebtItem]:
        """
        Gather monthly obligations.

        Sources:
            1. credit_liabilities table (from credit report pull)
            2. Fallback to lead-level monthly_debts if no credit data
        """
        debts: List[DebtItem] = []

        # Try credit_liabilities table
        try:
            rows = self.db.execute(
                text("""
                    SELECT
                        cl.creditor_name,
                        cl.account_type,
                        cl.monthly_payment,
                        cl.balance,
                        cl.months_remaining,
                        cl.is_cosigned,
                        cl.high_credit
                    FROM credit_liabilities cl
                    JOIN loans l ON l.id = cl.loan_id
                    WHERE cl.loan_id = :loan_id
                      AND l.organization_id = :org_id
                      AND cl.status = 'open'
                    ORDER BY cl.monthly_payment DESC
                """),
                {"loan_id": loan_id, "org_id": org_id},
            ).fetchall()

            for row in rows:
                mapping = dict(row._mapping) if hasattr(row, "_mapping") else {}
                account_type = (mapping.get("account_type") or "other").lower()
                monthly = _to_decimal(mapping.get("monthly_payment"))
                balance = _to_decimal(mapping.get("balance"))
                months_rem = mapping.get("months_remaining")

                # For revolving with no payment reported, use 1% of balance
                if account_type == "revolving" and (monthly is None or monthly <= ZERO):
                    if balance and balance > ZERO:
                        monthly = (balance * REVOLVING_MIN_PAYMENT_PCT).quantize(
                            TWO_PLACES, rounding=ROUND_HALF_UP
                        )
                        monthly = max(monthly, Decimal("25.00"))

                if monthly is None:
                    monthly = ZERO

                # Check if excludable (installment with < 10 months remaining)
                can_exclude = False
                exclusion_reason = None
                if (
                    account_type == "installment"
                    and months_rem is not None
                    and months_rem <= MONTHS_REMAINING_EXCLUDE_THRESHOLD
                ):
                    can_exclude = True
                    exclusion_reason = (
                        f"Installment debt with {months_rem} months remaining "
                        f"(< {MONTHS_REMAINING_EXCLUDE_THRESHOLD}). May be excluded from DTI."
                    )

                debts.append(DebtItem(
                    creditor=mapping.get("creditor_name") or "Unknown",
                    account_type=account_type,
                    monthly_payment=monthly,
                    balance=balance or ZERO,
                    months_remaining=months_rem,
                    is_co_signed=bool(mapping.get("is_cosigned")),
                    can_be_excluded=can_exclude,
                    exclusion_reason=exclusion_reason,
                    payoff_amount=balance,
                ))

        except Exception as e:
            logger.warning(
                f"Failed to query credit_liabilities for loan {loan_id}: {e}"
            )

        # Fallback: lead-level monthly_debts
        if not debts:
            try:
                lead_row = self.db.execute(
                    text("""
                        SELECT ld.monthly_debts
                        FROM leads ld
                        JOIN loans l ON l.loan_number = ld.loan_number
                        WHERE l.id = :loan_id
                          AND l.organization_id = :org_id
                          AND ld.monthly_debts IS NOT NULL
                          AND ld.monthly_debts > 0
                        LIMIT 1
                    """),
                    {"loan_id": loan_id, "org_id": org_id},
                ).fetchone()

                if lead_row:
                    monthly_debts_val = _to_decimal(
                        lead_row._mapping.get("monthly_debts")
                        if hasattr(lead_row, "_mapping")
                        else lead_row[0]
                    )
                    if monthly_debts_val and monthly_debts_val > ZERO:
                        debts.append(DebtItem(
                            creditor="Aggregate from application",
                            account_type="aggregate",
                            monthly_payment=monthly_debts_val,
                            balance=ZERO,
                            months_remaining=None,
                        ))
            except Exception as e:
                logger.warning(
                    f"Failed to query lead debts for loan {loan_id}: {e}"
                )

        return debts

    async def _estimate_coborrower_income(
        self,
        org_id: int,
        loan_id: int,
    ) -> Optional[Decimal]:
        """Estimate co-borrower income from lead data if available."""
        try:
            row = self.db.execute(
                text("""
                    SELECT ld.annual_income
                    FROM leads ld
                    JOIN loans l ON l.loan_number = ld.loan_number
                    WHERE l.id = :loan_id
                      AND l.organization_id = :org_id
                      AND ld.co_applicant_name IS NOT NULL
                      AND ld.co_applicant_name != ''
                    LIMIT 1
                """),
                {"loan_id": loan_id, "org_id": org_id},
            ).fetchone()

            # If there is a co-applicant but no separate income record,
            # we cannot estimate. Return None.
            return None

        except Exception as e:
            logger.warning(f"Co-borrower income lookup failed: {e}")
            return None

    async def _estimate_asset_depletion_income(
        self,
        org_id: int,
        loan_id: int,
    ) -> Optional[Decimal]:
        """
        Estimate asset depletion income.

        Formula: (eligible liquid assets - reserves needed) / remaining loan term months
        Retirement accounts counted at 60% of value.
        """
        try:
            row = self.db.execute(
                text("""
                    SELECT
                        SUM(
                            CASE
                                WHEN ba.account_type IN ('retirement', '401k', 'ira')
                                THEN ba.balance * 0.60
                                ELSE ba.balance
                            END
                        ) AS total_eligible
                    FROM borrower_assets ba
                    JOIN loans l ON l.id = ba.loan_id
                    WHERE ba.loan_id = :loan_id
                      AND l.organization_id = :org_id
                      AND ba.account_type IN (
                          'checking', 'savings', 'money_market',
                          'investment', 'retirement', '401k', 'ira', 'brokerage'
                      )
                      AND ba.balance > 0
                """),
                {"loan_id": loan_id, "org_id": org_id},
            ).fetchone()

            if not row:
                return None

            total_eligible = _to_decimal(
                row._mapping.get("total_eligible")
                if hasattr(row, "_mapping")
                else row[0]
            )

            if not total_eligible or total_eligible <= ZERO:
                return None

            # Get loan term
            loan = await self._get_loan(org_id, loan_id)
            if not loan:
                return None

            term_months = loan.get("term") or 360

            # Reserve requirement: 6 months PITIA
            pitia_obj = await self._build_pitia(loan)
            reserve_needed = pitia_obj.total * 6

            net_eligible = total_eligible - reserve_needed
            if net_eligible <= ZERO:
                return None

            monthly_income = (net_eligible / Decimal(str(term_months))).quantize(
                TWO_PLACES, rounding=ROUND_HALF_UP
            )

            return monthly_income

        except Exception as e:
            logger.warning(f"Asset depletion income lookup failed: {e}")
            return None

    async def _get_reserves_months(
        self,
        org_id: int,
        loan_id: int,
        pitia_monthly: Decimal,
    ) -> Optional[int]:
        """Calculate months of PITIA in reserves."""
        if pitia_monthly <= ZERO:
            return None

        try:
            row = self.db.execute(
                text("""
                    SELECT COALESCE(SUM(ba.balance), 0) AS total_liquid
                    FROM borrower_assets ba
                    JOIN loans l ON l.id = ba.loan_id
                    WHERE ba.loan_id = :loan_id
                      AND l.organization_id = :org_id
                      AND ba.account_type IN (
                          'checking', 'savings', 'money_market',
                          'investment', 'brokerage'
                      )
                      AND ba.balance > 0
                """),
                {"loan_id": loan_id, "org_id": org_id},
            ).fetchone()

            if not row:
                return None

            total_liquid = _to_decimal(
                row._mapping.get("total_liquid")
                if hasattr(row, "_mapping")
                else row[0]
            )

            if total_liquid is None or total_liquid <= ZERO:
                return None

            months = int(total_liquid / pitia_monthly)
            return months

        except Exception as e:
            logger.warning(f"Reserves lookup failed: {e}")
            return None

    async def _get_credit_score(
        self,
        org_id: int,
        loan_id: int,
    ) -> Optional[int]:
        """Get borrower credit score from lead or credit pull."""
        try:
            row = self.db.execute(
                text("""
                    SELECT ld.credit_score
                    FROM leads ld
                    JOIN loans l ON l.loan_number = ld.loan_number
                    WHERE l.id = :loan_id
                      AND l.organization_id = :org_id
                      AND ld.credit_score IS NOT NULL
                    LIMIT 1
                """),
                {"loan_id": loan_id, "org_id": org_id},
            ).fetchone()

            if row:
                score = (
                    row._mapping.get("credit_score")
                    if hasattr(row, "_mapping")
                    else row[0]
                )
                return int(score) if score else None

            return None

        except Exception as e:
            logger.warning(f"Credit score lookup failed: {e}")
            return None

    @staticmethod
    def _normalize_program(program_str: str) -> LoanProgram:
        """Normalize a loan type string to a LoanProgram enum."""
        normalized = program_str.strip().lower().replace("-", "_").replace(" ", "_")

        mapping = {
            "conventional": LoanProgram.CONVENTIONAL,
            "conv": LoanProgram.CONVENTIONAL,
            "fnma": LoanProgram.CONVENTIONAL,
            "fannie": LoanProgram.CONVENTIONAL,
            "freddie": LoanProgram.CONVENTIONAL,
            "fhlmc": LoanProgram.CONVENTIONAL,
            "fha": LoanProgram.FHA,
            "va": LoanProgram.VA,
            "usda": LoanProgram.USDA,
            "rural": LoanProgram.USDA,
            "non_qm": LoanProgram.NON_QM,
            "nonqm": LoanProgram.NON_QM,
            "non_qualified": LoanProgram.NON_QM,
            "jumbo": LoanProgram.JUMBO,
        }

        return mapping.get(normalized, LoanProgram.CONVENTIONAL)


# =============================================================================
# MODULE-LEVEL HELPERS
# =============================================================================

def _to_decimal(value: Any) -> Decimal:
    """Safely convert a value to Decimal."""
    if value is None:
        return ZERO
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value)).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError, TypeError):
        return ZERO


def _fmt_currency(amount: Decimal) -> str:
    """Format a Decimal as currency."""
    return f"${float(amount):,.2f}"


def _calculate_monthly_pi(
    loan_amount: Decimal,
    annual_rate: Decimal,
    term_months: int,
) -> Decimal:
    """
    Calculate monthly principal and interest using the standard
    amortization formula.

    M = P * [r(1+r)^n] / [(1+r)^n - 1]

    Where:
        P = loan amount
        r = monthly interest rate (annual / 12 / 100)
        n = total number of payments (term in months)
    """
    if loan_amount <= ZERO or annual_rate <= ZERO or term_months <= 0:
        return ZERO

    # Convert annual rate percentage to monthly decimal
    monthly_rate = float(annual_rate) / 100.0 / 12.0

    if monthly_rate == 0:
        return (loan_amount / Decimal(str(term_months))).quantize(
            TWO_PLACES, rounding=ROUND_HALF_UP
        )

    # Amortization formula
    factor = math.pow(1 + monthly_rate, term_months)
    payment = float(loan_amount) * (monthly_rate * factor) / (factor - 1)

    return Decimal(str(payment)).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


# =============================================================================
# FACTORY
# =============================================================================

def get_dti_optimizer_service(db: Session) -> DTIOptimizerService:
    """
    Factory function returning a DTIOptimizerService.

    Usage:
        service = get_dti_optimizer_service(db)
        result = await service.calculate_dti(org_id=1, loan_id=42)
    """
    return DTIOptimizerService(db)
