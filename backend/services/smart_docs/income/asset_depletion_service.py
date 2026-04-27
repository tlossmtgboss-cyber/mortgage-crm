"""
Asset Depletion Income Calculator Service

Calculates qualifying income from asset depletion for borrowers with
significant liquid assets but limited traditional income -- common for
retirees, early-retirees, and high-net-worth borrowers.

Implements both Fannie Mae (Selling Guide B3-3.1-09) and Freddie Mac
(Guide Section 5306.1) asset depletion methodologies with real discount
factors, account-type eligibility rules, and sustainability analysis.

Integrates with:
    - income_calculations / income_sources for result persistence
    - income_verification_tasks for LO follow-up items
    - smart_documents / smart_document_extractions for account statements
    - IncomeCalculatorService for combination income analysis

Key formulas:
    Fannie Mae:
        Monthly Income = (Eligible Assets * Discount - Down Payment - Closing Costs)
                         / Remaining Loan Term in Months

    Freddie Mac:
        Monthly Income = (Eligible Non-Retirement Assets * Discount)
                         / min(Remaining Loan Term, 120) months
        Retirement assets only eligible if borrower >= 62
        Max 80% LTV

Usage:
    from services.smart_docs.income.asset_depletion_service import (
        AssetDepletionService,
        get_asset_depletion_service,
    )

    service = get_asset_depletion_service(db, org_id=42)
    result = await service.calculate_asset_depletion_income(
        loan_id=100,
        accounts=[...],
        borrower_age=67,
        loan_term_months=360,
        down_payment=Decimal("80000"),
        closing_costs=Decimal("12000"),
    )
"""

import enum
import json
import logging
import time
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import text
from sqlalchemy.orm import Session

from services.smart_docs.service_registry import OrgAwareService

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ZERO = Decimal("0.00")
TWO_PLACES = Decimal("0.01")
FOUR_PLACES = Decimal("0.0001")

# Minimum age for penalty-free retirement withdrawals (IRS 59-1/2 rule)
IRA_PENALTY_FREE_AGE = Decimal("59.5")

# Freddie Mac minimum age for retirement account eligibility
FREDDIE_RETIREMENT_MIN_AGE = 62

# Freddie Mac maximum amortization period for asset depletion (months)
FREDDIE_MAX_AMORT_MONTHS = 120

# Freddie Mac maximum LTV for asset depletion qualification
FREDDIE_MAX_LTV = Decimal("80.00")

# Minimum document seasoning period (days) -- 60-day average balance
SEASONING_PERIOD_DAYS = 60

# Large deposit threshold as percentage of stated monthly income
LARGE_DEPOSIT_THRESHOLD_PCT = Decimal("50.0")

# Sustainability warning: if monthly draw exceeds this percentage of balance
SUSTAINABILITY_WARN_DRAW_PCT = Decimal("1.5")  # 1.5% monthly = ~18% annual
SUSTAINABILITY_CRITICAL_DRAW_PCT = Decimal("2.5")  # 2.5% monthly = ~30% annual


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class AccountType(str, enum.Enum):
    """Asset account types for depletion income calculation."""
    CHECKING = "checking"
    SAVINGS = "savings"
    MONEY_MARKET = "money_market"
    CD = "cd"
    STOCKS = "stocks"
    BONDS = "bonds"
    MUTUAL_FUNDS = "mutual_funds"
    ETF = "etf"
    BROKERAGE = "brokerage"
    IRA_TRADITIONAL = "ira_traditional"
    IRA_ROTH = "ira_roth"
    ROTH_401K = "roth_401k"
    TRADITIONAL_401K = "traditional_401k"
    SEP_IRA = "sep_ira"
    SIMPLE_IRA = "simple_ira"
    PENSION = "pension"
    ANNUITY = "annuity"
    # Ineligible types -- included so callers can submit and receive a
    # structured ineligibility result rather than an opaque rejection.
    BUSINESS = "business"
    RESTRICTED_STOCK = "restricted_stock"
    NON_VESTED_OPTIONS = "non_vested_options"
    LIFE_INSURANCE_CSV = "life_insurance_csv"
    CRYPTO = "crypto"
    NFT = "nft"
    REAL_ESTATE_EQUITY = "real_estate_equity"
    TRUST = "trust"


class OwnershipType(str, enum.Enum):
    """Account ownership classification."""
    SOLE = "sole"
    JOINT_BORROWER = "joint_borrower"       # joint with co-borrower on loan
    JOINT_NON_BORROWER = "joint_non_borrower"  # joint with non-borrower
    CUSTODIAL = "custodial"
    TRUST = "trust"


class AgencyType(str, enum.Enum):
    """Loan agency / investor type."""
    FANNIE_MAE = "fannie_mae"
    FREDDIE_MAC = "freddie_mac"
    FHA = "fha"
    VA = "va"
    NON_QM = "non_qm"


class SustainabilityRating(str, enum.Enum):
    """Asset sustainability through loan term."""
    STRONG = "strong"       # Assets easily cover full term
    ADEQUATE = "adequate"   # Assets cover term with modest growth assumption
    MARGINAL = "marginal"   # Assets may not last full term
    INSUFFICIENT = "insufficient"  # Assets clearly insufficient


# ---------------------------------------------------------------------------
# Discount Factor Tables
# ---------------------------------------------------------------------------

# Fannie Mae discount factors per Selling Guide B3-3.1-09
FANNIE_DISCOUNT_FACTORS: Dict[str, Dict[str, Decimal]] = {
    # Cash and cash equivalents: 100%
    "cash_equivalents": {
        AccountType.CHECKING: Decimal("1.00"),
        AccountType.SAVINGS: Decimal("1.00"),
        AccountType.MONEY_MARKET: Decimal("1.00"),
        AccountType.CD: Decimal("1.00"),
    },
    # Marketable securities: 70% (30% volatility discount)
    "marketable_securities": {
        AccountType.STOCKS: Decimal("0.70"),
        AccountType.BONDS: Decimal("0.70"),
        AccountType.MUTUAL_FUNDS: Decimal("0.70"),
        AccountType.ETF: Decimal("0.70"),
        AccountType.BROKERAGE: Decimal("0.70"),
    },
    # Retirement accounts -- factor depends on borrower age
    # < 59.5: 60% (early withdrawal 10% penalty + estimated ~30% tax)
    # >= 59.5: 70% (no penalty, estimated ~30% tax)
    "retirement_under_59_5": {
        AccountType.IRA_TRADITIONAL: Decimal("0.60"),
        AccountType.IRA_ROTH: Decimal("0.60"),
        AccountType.ROTH_401K: Decimal("0.60"),
        AccountType.TRADITIONAL_401K: Decimal("0.60"),
        AccountType.SEP_IRA: Decimal("0.60"),
        AccountType.SIMPLE_IRA: Decimal("0.60"),
        AccountType.PENSION: Decimal("0.60"),
        AccountType.ANNUITY: Decimal("0.60"),
    },
    "retirement_over_59_5": {
        AccountType.IRA_TRADITIONAL: Decimal("0.70"),
        AccountType.IRA_ROTH: Decimal("0.70"),
        AccountType.ROTH_401K: Decimal("0.70"),
        AccountType.TRADITIONAL_401K: Decimal("0.70"),
        AccountType.SEP_IRA: Decimal("0.70"),
        AccountType.SIMPLE_IRA: Decimal("0.70"),
        AccountType.PENSION: Decimal("0.70"),
        AccountType.ANNUITY: Decimal("0.70"),
    },
}

# Freddie Mac discount factors per Guide 5306.1
# Non-retirement assets only (retirement requires age >= 62)
FREDDIE_DISCOUNT_FACTORS: Dict[str, Decimal] = {
    AccountType.CHECKING: Decimal("1.00"),
    AccountType.SAVINGS: Decimal("1.00"),
    AccountType.MONEY_MARKET: Decimal("1.00"),
    AccountType.CD: Decimal("1.00"),
    AccountType.STOCKS: Decimal("0.70"),
    AccountType.BONDS: Decimal("0.70"),
    AccountType.MUTUAL_FUNDS: Decimal("0.70"),
    AccountType.ETF: Decimal("0.70"),
    AccountType.BROKERAGE: Decimal("0.70"),
    # Retirement accounts (only if borrower >= 62)
    AccountType.IRA_TRADITIONAL: Decimal("0.70"),
    AccountType.IRA_ROTH: Decimal("0.70"),
    AccountType.ROTH_401K: Decimal("0.70"),
    AccountType.TRADITIONAL_401K: Decimal("0.70"),
    AccountType.SEP_IRA: Decimal("0.70"),
    AccountType.SIMPLE_IRA: Decimal("0.70"),
    AccountType.PENSION: Decimal("0.70"),
    AccountType.ANNUITY: Decimal("0.70"),
}

# Account types that are always ineligible for asset depletion
INELIGIBLE_ACCOUNT_TYPES = frozenset({
    AccountType.BUSINESS,
    AccountType.RESTRICTED_STOCK,
    AccountType.NON_VESTED_OPTIONS,
    AccountType.LIFE_INSURANCE_CSV,
    AccountType.CRYPTO,
    AccountType.NFT,
    AccountType.REAL_ESTATE_EQUITY,
})

# Retirement account types
RETIREMENT_ACCOUNT_TYPES = frozenset({
    AccountType.IRA_TRADITIONAL,
    AccountType.IRA_ROTH,
    AccountType.ROTH_401K,
    AccountType.TRADITIONAL_401K,
    AccountType.SEP_IRA,
    AccountType.SIMPLE_IRA,
    AccountType.PENSION,
    AccountType.ANNUITY,
})

# Cash-equivalent account types
CASH_EQUIVALENT_TYPES = frozenset({
    AccountType.CHECKING,
    AccountType.SAVINGS,
    AccountType.MONEY_MARKET,
    AccountType.CD,
})

# Marketable securities types
MARKETABLE_SECURITIES_TYPES = frozenset({
    AccountType.STOCKS,
    AccountType.BONDS,
    AccountType.MUTUAL_FUNDS,
    AccountType.ETF,
    AccountType.BROKERAGE,
})

# Federal income tax bracket approximation for distribution impact
# Simplified 2024/2025 brackets for single filer (used for estimation only)
FEDERAL_TAX_BRACKETS: List[Tuple[Decimal, Decimal]] = [
    (Decimal("11600"), Decimal("0.10")),
    (Decimal("47150"), Decimal("0.12")),
    (Decimal("100525"), Decimal("0.22")),
    (Decimal("191950"), Decimal("0.24")),
    (Decimal("243725"), Decimal("0.32")),
    (Decimal("609350"), Decimal("0.35")),
    (Decimal("999999999"), Decimal("0.37")),
]

# Early withdrawal penalty rate (IRS 10% penalty for < 59.5)
EARLY_WITHDRAWAL_PENALTY_RATE = Decimal("0.10")

# Required Minimum Distribution start age (SECURE Act 2.0: 73 as of 2023)
RMD_START_AGE = 73

# RMD divisor table (IRS Uniform Lifetime Table, abbreviated for key ages)
# Maps age -> divisor. Actual table runs 72-120+.
RMD_DIVISOR_TABLE: Dict[int, Decimal] = {
    72: Decimal("27.4"),
    73: Decimal("26.5"),
    74: Decimal("25.5"),
    75: Decimal("24.6"),
    76: Decimal("23.7"),
    77: Decimal("22.9"),
    78: Decimal("22.0"),
    79: Decimal("21.1"),
    80: Decimal("20.2"),
    81: Decimal("19.4"),
    82: Decimal("18.5"),
    83: Decimal("17.7"),
    84: Decimal("16.8"),
    85: Decimal("16.0"),
    86: Decimal("15.2"),
    87: Decimal("14.4"),
    88: Decimal("13.7"),
    89: Decimal("12.9"),
    90: Decimal("12.2"),
}


# ---------------------------------------------------------------------------
# Data Classes
# ---------------------------------------------------------------------------

@dataclass
class AssetAccount:
    """Input: a single asset account for depletion analysis."""
    account_type: AccountType
    institution_name: str
    account_number_last4: str
    current_balance: Decimal
    sixty_day_average_balance: Optional[Decimal] = None
    ownership_type: OwnershipType = OwnershipType.SOLE
    is_pledged: bool = False
    has_liens: bool = False
    is_vested: bool = True  # For retirement accounts
    statement_date: Optional[date] = None
    months_of_statements: int = 0  # How many months of statements provided
    large_deposits: Optional[List[Dict[str, Any]]] = None
    document_ids: Optional[List[int]] = None


@dataclass
class EligibilityResult:
    """Result of account eligibility check."""
    account_type: AccountType
    is_eligible: bool
    eligible_balance: Decimal = ZERO
    discount_factor: Decimal = ZERO
    discounted_value: Decimal = ZERO
    ownership_adjustment: Decimal = Decimal("1.00")  # 1.0 = full, 0.5 = joint
    ineligibility_reasons: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    documentation_requirements: List[str] = field(default_factory=list)


@dataclass
class DiscountedAccount:
    """Single account after discount factor application."""
    account: AssetAccount
    eligibility: EligibilityResult
    raw_balance: Decimal
    ownership_adjusted_balance: Decimal
    seasoned_balance: Decimal  # min(current, 60-day avg) or current if no avg
    discount_factor: Decimal
    discounted_value: Decimal


@dataclass
class DiscountedAssets:
    """Aggregated result after applying discount factors to all accounts."""
    accounts: List[DiscountedAccount]
    total_raw_balance: Decimal = ZERO
    total_eligible_balance: Decimal = ZERO
    total_discounted_value: Decimal = ZERO
    ineligible_accounts: List[Dict[str, Any]] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    by_category: Dict[str, Decimal] = field(default_factory=dict)


@dataclass
class SustainabilityResult:
    """Sustainability analysis for asset depletion through loan term."""
    rating: SustainabilityRating
    total_eligible_assets: Decimal
    monthly_depletion_income: Decimal
    loan_term_months: int
    total_draw_over_term: Decimal
    remaining_assets_at_term: Decimal
    monthly_draw_rate_pct: Decimal   # monthly draw / total assets * 100
    annual_draw_rate_pct: Decimal    # monthly * 12
    years_assets_will_last: Decimal
    conservative_years: Decimal      # assuming 0% growth
    moderate_years: Decimal          # assuming 3% annual growth
    aggressive_years: Decimal        # assuming 6% annual growth
    recommendations: List[str] = field(default_factory=list)


@dataclass
class TaxImpactAnalysis:
    """Tax impact analysis for asset distributions."""
    annual_distribution_amount: Decimal
    estimated_federal_tax: Decimal
    estimated_state_tax: Decimal  # placeholder -- state-dependent
    early_withdrawal_penalty: Decimal
    total_tax_impact: Decimal
    effective_tax_rate: Decimal
    after_tax_annual_income: Decimal
    after_tax_monthly_income: Decimal
    rmd_amount: Optional[Decimal] = None
    rmd_coordination_notes: List[str] = field(default_factory=list)
    capital_gains_notes: List[str] = field(default_factory=list)


@dataclass
class AgencyRules:
    """Agency-specific rules for asset depletion."""
    agency: AgencyType
    max_ltv: Optional[Decimal]
    max_amortization_months: Optional[int]
    retirement_accounts_eligible: bool
    retirement_min_age: Optional[int]
    discount_factors: Dict[str, Decimal]
    eligible_account_types: List[AccountType]
    additional_requirements: List[str]
    documentation_requirements: List[str]


@dataclass
class AssetDepletionResult:
    """Complete asset depletion income calculation result."""
    loan_id: int
    borrower_age: Decimal
    agency: AgencyType

    # Core calculation
    total_eligible_assets: Decimal
    total_discounted_assets: Decimal
    down_payment_deduction: Decimal
    closing_costs_deduction: Decimal
    net_eligible_assets: Decimal
    loan_term_months: int
    effective_amort_months: int  # May differ from loan term (Freddie 120 cap)
    monthly_qualifying_income: Decimal
    annual_qualifying_income: Decimal

    # Detail breakdowns
    discounted_assets: DiscountedAssets
    sustainability: SustainabilityResult
    tax_impact: TaxImpactAnalysis

    # Flags and recommendations
    flags: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    documentation_requirements: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)

    # Combination income analysis
    other_income_monthly: Decimal = ZERO
    combined_qualifying_monthly: Decimal = ZERO
    double_counting_warnings: List[str] = field(default_factory=list)

    # Confidence and metadata
    confidence: int = 0  # 0-100
    calculation_method: str = "asset_depletion"
    success: bool = True
    error: Optional[str] = None
    tasks_to_create: List[Dict[str, Any]] = field(default_factory=list)


# =============================================================================
# SERVICE
# =============================================================================

class AssetDepletionService(OrgAwareService):
    """
    Asset depletion income calculator following Fannie Mae and Freddie Mac
    guidelines.

    Calculates qualifying monthly income from liquid assets for borrowers
    who have substantial savings but limited traditional income streams.
    Common use cases: retirees, early retirees, high-net-worth individuals.

    Fannie Mae methodology (B3-3.1-09):
        1. Sum eligible assets (checking, savings, CDs, stocks, bonds,
           mutual funds, retirement accounts)
        2. Apply discount factors (100% cash, 70% securities,
           60-70% retirement based on age)
        3. Subtract down payment and closing costs
        4. Divide by remaining loan term in months

    Freddie Mac methodology (5306.1):
        1. Non-retirement assets only (retirement requires age >= 62)
        2. Apply discount factors (same rates)
        3. Divide by min(remaining loan term, 120 months)
        4. Maximum 80% LTV
    """

    def __init__(
        self,
        db: Session,
        org_id: int,
        user_id: Optional[int] = None,
    ):
        super().__init__(db=db, org_id=org_id, user_id=user_id)

    # =========================================================================
    # 1. MAIN ENTRY POINT
    # =========================================================================

    async def calculate_asset_depletion_income(
        self,
        loan_id: int,
        accounts: List[AssetAccount],
        borrower_age: Decimal,
        loan_term_months: int,
        down_payment: Decimal = ZERO,
        closing_costs: Decimal = ZERO,
        agency: AgencyType = AgencyType.FANNIE_MAE,
        other_qualifying_income_monthly: Decimal = ZERO,
        state_code: Optional[str] = None,
        borrower_id: Optional[int] = None,
    ) -> AssetDepletionResult:
        """
        Calculate qualifying monthly income from asset depletion.

        Args:
            loan_id: Loan ID (verified against org_id for tenant isolation).
            accounts: List of asset accounts to evaluate.
            borrower_age: Borrower's current age as Decimal (e.g. 67.5).
            loan_term_months: Remaining loan term in months (e.g. 360 for 30-year).
            down_payment: Down payment amount to deduct from eligible assets.
            closing_costs: Closing costs to deduct from eligible assets.
            agency: Agency/investor type for guideline selection.
            other_qualifying_income_monthly: Traditional income already qualified
                (used to check for double-counting with retirement income).
            state_code: Two-letter state code for state tax estimation.
            borrower_id: Optional borrower ID for result persistence.

        Returns:
            AssetDepletionResult with monthly qualifying income and full analysis.
        """
        start_ms = int(time.time() * 1000)

        try:
            # Verify tenant isolation
            await self._verify_loan_org(loan_id)

            # Validate inputs
            validation_errors = self._validate_inputs(
                accounts, borrower_age, loan_term_months, down_payment, closing_costs,
            )
            if validation_errors:
                return AssetDepletionResult(
                    loan_id=loan_id,
                    borrower_age=borrower_age,
                    agency=agency,
                    total_eligible_assets=ZERO,
                    total_discounted_assets=ZERO,
                    down_payment_deduction=down_payment,
                    closing_costs_deduction=closing_costs,
                    net_eligible_assets=ZERO,
                    loan_term_months=loan_term_months,
                    effective_amort_months=loan_term_months,
                    monthly_qualifying_income=ZERO,
                    annual_qualifying_income=ZERO,
                    discounted_assets=DiscountedAssets(accounts=[]),
                    sustainability=SustainabilityResult(
                        rating=SustainabilityRating.INSUFFICIENT,
                        total_eligible_assets=ZERO,
                        monthly_depletion_income=ZERO,
                        loan_term_months=loan_term_months,
                        total_draw_over_term=ZERO,
                        remaining_assets_at_term=ZERO,
                        monthly_draw_rate_pct=ZERO,
                        annual_draw_rate_pct=ZERO,
                        years_assets_will_last=ZERO,
                        conservative_years=ZERO,
                        moderate_years=ZERO,
                        aggressive_years=ZERO,
                    ),
                    tax_impact=TaxImpactAnalysis(
                        annual_distribution_amount=ZERO,
                        estimated_federal_tax=ZERO,
                        estimated_state_tax=ZERO,
                        early_withdrawal_penalty=ZERO,
                        total_tax_impact=ZERO,
                        effective_tax_rate=ZERO,
                        after_tax_annual_income=ZERO,
                        after_tax_monthly_income=ZERO,
                    ),
                    flags=validation_errors,
                    success=False,
                    error="; ".join(validation_errors),
                )

            # Step 1: Check agency-specific prerequisites
            agency_rules = self.get_agency_specific_rules(agency, borrower_age)
            prerequisite_flags = await self._check_agency_prerequisites(
                loan_id, agency, agency_rules,
            )

            # Step 2: Validate each account's eligibility
            eligibility_results = [
                self.validate_account_eligibility(
                    acct.account_type,
                    acct.current_balance,
                    borrower_age,
                    agency=agency,
                    ownership_type=acct.ownership_type,
                    is_pledged=acct.is_pledged,
                    has_liens=acct.has_liens,
                    is_vested=acct.is_vested,
                    months_of_statements=acct.months_of_statements,
                    sixty_day_average=acct.sixty_day_average_balance,
                )
                for acct in accounts
            ]

            # Step 3: Apply discount factors
            discounted = self.apply_discount_factors(accounts, borrower_age, agency)

            # Step 4: Calculate net eligible assets
            net_eligible = (
                discounted.total_discounted_value - down_payment - closing_costs
            ).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)

            if net_eligible < ZERO:
                net_eligible = ZERO

            # Step 5: Determine effective amortization period
            if agency == AgencyType.FREDDIE_MAC:
                effective_months = min(loan_term_months, FREDDIE_MAX_AMORT_MONTHS)
            else:
                effective_months = loan_term_months

            # Step 6: Calculate monthly qualifying income
            if effective_months > 0 and net_eligible > ZERO:
                monthly_income = (net_eligible / effective_months).quantize(
                    TWO_PLACES, rounding=ROUND_HALF_UP,
                )
            else:
                monthly_income = ZERO

            annual_income = (monthly_income * 12).quantize(
                TWO_PLACES, rounding=ROUND_HALF_UP,
            )

            # Step 7: Sustainability analysis
            sustainability = self.calculate_sustainability(
                discounted.total_discounted_value,
                monthly_income,
                loan_term_months,
            )

            # Step 8: Tax impact analysis
            tax_impact = self._calculate_tax_impact(
                accounts,
                annual_income,
                borrower_age,
                state_code,
            )

            # Step 9: Check for double-counting with traditional income
            double_counting = self._check_double_counting(
                accounts, other_qualifying_income_monthly, loan_id,
            )

            # Step 10: Build documentation requirements
            doc_requirements = self._build_documentation_requirements(
                accounts, eligibility_results,
            )

            # Step 11: Aggregate flags and recommendations
            all_flags = list(prerequisite_flags)
            all_warnings: List[str] = list(discounted.warnings)
            all_recommendations: List[str] = list(sustainability.recommendations)

            for er in eligibility_results:
                all_warnings.extend(er.warnings)

            if monthly_income == ZERO and accounts:
                all_flags.append("ZERO_QUALIFYING_INCOME")
                all_recommendations.append(
                    "No qualifying income from asset depletion. Review account "
                    "eligibility and ensure sufficient assets after deductions."
                )

            if sustainability.rating == SustainabilityRating.MARGINAL:
                all_flags.append("MARGINAL_SUSTAINABILITY")
            elif sustainability.rating == SustainabilityRating.INSUFFICIENT:
                all_flags.append("INSUFFICIENT_SUSTAINABILITY")

            all_flags.extend(double_counting.get("flags", []))
            all_warnings.extend(double_counting.get("warnings", []))

            # Large deposit analysis
            for acct in accounts:
                if acct.large_deposits:
                    for dep in acct.large_deposits:
                        dep_amount = Decimal(str(dep.get("amount", 0)))
                        if dep_amount > ZERO:
                            all_flags.append(
                                f"LARGE_DEPOSIT_{acct.institution_name}_"
                                f"{dep_amount:.0f}"
                            )
                            all_recommendations.append(
                                f"Source {dep_amount:,.2f} large deposit at "
                                f"{acct.institution_name} "
                                f"(date: {dep.get('date', 'unknown')})"
                            )

            # Confidence scoring
            confidence = self._calculate_confidence(
                accounts, eligibility_results, discounted, sustainability,
            )

            # Step 12: Build tasks
            tasks = self._generate_tasks(
                loan_id, borrower_id, all_flags, all_recommendations,
                doc_requirements, accounts,
            )

            combined_monthly = (
                monthly_income + other_qualifying_income_monthly
            ).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)

            result = AssetDepletionResult(
                loan_id=loan_id,
                borrower_age=borrower_age,
                agency=agency,
                total_eligible_assets=discounted.total_eligible_balance,
                total_discounted_assets=discounted.total_discounted_value,
                down_payment_deduction=down_payment,
                closing_costs_deduction=closing_costs,
                net_eligible_assets=net_eligible,
                loan_term_months=loan_term_months,
                effective_amort_months=effective_months,
                monthly_qualifying_income=monthly_income,
                annual_qualifying_income=annual_income,
                discounted_assets=discounted,
                sustainability=sustainability,
                tax_impact=tax_impact,
                flags=all_flags,
                warnings=all_warnings,
                documentation_requirements=doc_requirements,
                recommendations=all_recommendations,
                other_income_monthly=other_qualifying_income_monthly,
                combined_qualifying_monthly=combined_monthly,
                double_counting_warnings=double_counting.get("warnings", []),
                confidence=confidence,
                tasks_to_create=tasks,
            )

            # Step 13: Persist
            duration_ms = int(time.time() * 1000) - start_ms
            await self._save_calculation(result, borrower_id, duration_ms)

            return result

        except Exception as e:
            logger.exception(
                f"Asset depletion calculation failed for loan={loan_id} "
                f"org={self.org_id}: {e}"
            )
            return AssetDepletionResult(
                loan_id=loan_id,
                borrower_age=borrower_age,
                agency=agency,
                total_eligible_assets=ZERO,
                total_discounted_assets=ZERO,
                down_payment_deduction=down_payment,
                closing_costs_deduction=closing_costs,
                net_eligible_assets=ZERO,
                loan_term_months=loan_term_months,
                effective_amort_months=loan_term_months,
                monthly_qualifying_income=ZERO,
                annual_qualifying_income=ZERO,
                discounted_assets=DiscountedAssets(accounts=[]),
                sustainability=SustainabilityResult(
                    rating=SustainabilityRating.INSUFFICIENT,
                    total_eligible_assets=ZERO,
                    monthly_depletion_income=ZERO,
                    loan_term_months=loan_term_months,
                    total_draw_over_term=ZERO,
                    remaining_assets_at_term=ZERO,
                    monthly_draw_rate_pct=ZERO,
                    annual_draw_rate_pct=ZERO,
                    years_assets_will_last=ZERO,
                    conservative_years=ZERO,
                    moderate_years=ZERO,
                    aggressive_years=ZERO,
                ),
                tax_impact=TaxImpactAnalysis(
                    annual_distribution_amount=ZERO,
                    estimated_federal_tax=ZERO,
                    estimated_state_tax=ZERO,
                    early_withdrawal_penalty=ZERO,
                    total_tax_impact=ZERO,
                    effective_tax_rate=ZERO,
                    after_tax_annual_income=ZERO,
                    after_tax_monthly_income=ZERO,
                ),
                success=False,
                error=str(e),
            )

    # =========================================================================
    # 2. ACCOUNT ELIGIBILITY VALIDATION
    # =========================================================================

    def validate_account_eligibility(
        self,
        account_type: AccountType,
        balance: Decimal,
        borrower_age: Decimal,
        agency: AgencyType = AgencyType.FANNIE_MAE,
        ownership_type: OwnershipType = OwnershipType.SOLE,
        is_pledged: bool = False,
        has_liens: bool = False,
        is_vested: bool = True,
        months_of_statements: int = 0,
        sixty_day_average: Optional[Decimal] = None,
    ) -> EligibilityResult:
        """
        Validate whether an account is eligible for asset depletion and
        determine the applicable discount factor.

        Args:
            account_type: Type of asset account.
            balance: Current account balance.
            borrower_age: Borrower's age as Decimal.
            agency: Agency type for guideline selection.
            ownership_type: Account ownership classification.
            is_pledged: Whether the account is pledged as collateral.
            has_liens: Whether there are liens against the account.
            is_vested: Whether retirement assets are fully vested.
            months_of_statements: Number of consecutive months of statements.
            sixty_day_average: 60-day average balance for seasoning.

        Returns:
            EligibilityResult with eligibility determination and discount factor.
        """
        reasons: List[str] = []
        warnings: List[str] = []
        doc_reqs: List[str] = []

        # --- Always ineligible types ---
        if account_type in INELIGIBLE_ACCOUNT_TYPES:
            reason_map = {
                AccountType.BUSINESS: "Business assets are not eligible for asset depletion",
                AccountType.RESTRICTED_STOCK: "Restricted stock is not liquid and ineligible",
                AccountType.NON_VESTED_OPTIONS: "Non-vested stock options are ineligible",
                AccountType.LIFE_INSURANCE_CSV: "Life insurance cash surrender value: eligibility varies by investor",
                AccountType.CRYPTO: "Cryptocurrency is not an eligible asset for agency loans",
                AccountType.NFT: "NFTs are not eligible assets for mortgage qualification",
                AccountType.REAL_ESTATE_EQUITY: "Real estate equity is not a liquid asset",
            }
            return EligibilityResult(
                account_type=account_type,
                is_eligible=False,
                ineligibility_reasons=[
                    reason_map.get(account_type, f"{account_type.value} is ineligible")
                ],
            )

        # --- Trust accounts: eligible only if borrower is beneficiary with
        #     unrestricted access ---
        if account_type == AccountType.TRUST:
            warnings.append(
                "Trust account: verify borrower has unrestricted access as "
                "beneficiary or trustee. Provide trust agreement."
            )
            doc_reqs.append("Complete trust agreement showing beneficiary rights")

        # --- Pledged / lien checks ---
        if is_pledged:
            reasons.append("Account is pledged as collateral and cannot be used")
            return EligibilityResult(
                account_type=account_type,
                is_eligible=False,
                ineligibility_reasons=reasons,
            )

        if has_liens:
            reasons.append("Account has liens and cannot be used until liens are released")
            return EligibilityResult(
                account_type=account_type,
                is_eligible=False,
                ineligibility_reasons=reasons,
            )

        # --- Vesting check for retirement accounts ---
        if account_type in RETIREMENT_ACCOUNT_TYPES and not is_vested:
            reasons.append(
                "Retirement account is not fully vested; only vested balance is eligible"
            )
            return EligibilityResult(
                account_type=account_type,
                is_eligible=False,
                ineligibility_reasons=reasons,
            )

        # --- Freddie Mac retirement age restriction ---
        if (
            agency == AgencyType.FREDDIE_MAC
            and account_type in RETIREMENT_ACCOUNT_TYPES
            and borrower_age < FREDDIE_RETIREMENT_MIN_AGE
        ):
            reasons.append(
                f"Freddie Mac requires borrower age >= {FREDDIE_RETIREMENT_MIN_AGE} "
                f"for retirement account eligibility (borrower is {borrower_age})"
            )
            return EligibilityResult(
                account_type=account_type,
                is_eligible=False,
                ineligibility_reasons=reasons,
            )

        # --- Determine ownership adjustment ---
        if ownership_type == OwnershipType.SOLE:
            ownership_adj = Decimal("1.00")
        elif ownership_type == OwnershipType.JOINT_BORROWER:
            # Joint with co-borrower on loan: 100% eligible
            ownership_adj = Decimal("1.00")
        elif ownership_type == OwnershipType.JOINT_NON_BORROWER:
            # Joint with non-borrower: use 50% per guidelines
            ownership_adj = Decimal("0.50")
            warnings.append(
                "Joint account with non-borrower: only 50% of balance is eligible"
            )
        elif ownership_type == OwnershipType.CUSTODIAL:
            reasons.append("Custodial accounts are not eligible (borrower is not owner)")
            return EligibilityResult(
                account_type=account_type,
                is_eligible=False,
                ineligibility_reasons=reasons,
            )
        elif ownership_type == OwnershipType.TRUST:
            ownership_adj = Decimal("1.00")
            warnings.append("Trust account: verify borrower access rights")
        else:
            ownership_adj = Decimal("1.00")

        # --- Determine discount factor ---
        discount_factor = self._get_discount_factor(
            account_type, borrower_age, agency,
        )

        # --- Determine seasoned balance ---
        if sixty_day_average is not None:
            seasoned_balance = min(balance, sixty_day_average)
            if sixty_day_average < balance:
                warnings.append(
                    f"60-day average ({sixty_day_average:,.2f}) is less than current "
                    f"balance ({balance:,.2f}); using lower seasoned balance"
                )
        else:
            seasoned_balance = balance
            if months_of_statements < 2:
                warnings.append(
                    "Less than 2 months of statements provided. 60-day average "
                    "balance cannot be verified."
                )

        # --- Calculate eligible and discounted values ---
        eligible_balance = (seasoned_balance * ownership_adj).quantize(
            TWO_PLACES, rounding=ROUND_HALF_UP,
        )
        discounted_value = (eligible_balance * discount_factor).quantize(
            TWO_PLACES, rounding=ROUND_HALF_UP,
        )

        # --- Documentation requirements ---
        if months_of_statements < 2:
            doc_reqs.append(
                "2 consecutive monthly statements required (or 1 quarterly statement)"
            )
        doc_reqs.append(f"Verify account ownership for {account_type.value} account")

        if account_type in RETIREMENT_ACCOUNT_TYPES:
            doc_reqs.append("Most recent retirement account statement")
            doc_reqs.append("Verify vesting schedule and withdrawal terms")
            if borrower_age < IRA_PENALTY_FREE_AGE:
                doc_reqs.append(
                    "Document early withdrawal provisions (borrower < 59.5)"
                )

        return EligibilityResult(
            account_type=account_type,
            is_eligible=True,
            eligible_balance=eligible_balance,
            discount_factor=discount_factor,
            discounted_value=discounted_value,
            ownership_adjustment=ownership_adj,
            warnings=warnings,
            documentation_requirements=doc_reqs,
        )

    # =========================================================================
    # 3. DISCOUNT FACTOR APPLICATION
    # =========================================================================

    def apply_discount_factors(
        self,
        accounts: List[AssetAccount],
        borrower_age: Decimal,
        agency: AgencyType = AgencyType.FANNIE_MAE,
    ) -> DiscountedAssets:
        """
        Apply agency-specific discount factors to all accounts and aggregate.

        Args:
            accounts: List of asset accounts.
            borrower_age: Borrower's current age.
            agency: Agency type for discount factor selection.

        Returns:
            DiscountedAssets with per-account and aggregate discounted values.
        """
        discounted_accounts: List[DiscountedAccount] = []
        ineligible: List[Dict[str, Any]] = []
        all_warnings: List[str] = []
        total_raw = ZERO
        total_eligible = ZERO
        total_discounted = ZERO
        by_category: Dict[str, Decimal] = {
            "cash_equivalents": ZERO,
            "marketable_securities": ZERO,
            "retirement": ZERO,
        }

        for acct in accounts:
            total_raw += acct.current_balance

            eligibility = self.validate_account_eligibility(
                account_type=acct.account_type,
                balance=acct.current_balance,
                borrower_age=borrower_age,
                agency=agency,
                ownership_type=acct.ownership_type,
                is_pledged=acct.is_pledged,
                has_liens=acct.has_liens,
                is_vested=acct.is_vested,
                months_of_statements=acct.months_of_statements,
                sixty_day_average=acct.sixty_day_average,
            )

            if not eligibility.is_eligible:
                ineligible.append({
                    "institution": acct.institution_name,
                    "account_type": acct.account_type.value,
                    "balance": float(acct.current_balance),
                    "reasons": eligibility.ineligibility_reasons,
                })
                continue

            # Determine seasoned balance
            if acct.sixty_day_average_balance is not None:
                seasoned = min(acct.current_balance, acct.sixty_day_average_balance)
            else:
                seasoned = acct.current_balance

            # Ownership adjustment
            ownership_adj = eligibility.ownership_adjustment
            adjusted_balance = (seasoned * ownership_adj).quantize(
                TWO_PLACES, rounding=ROUND_HALF_UP,
            )

            discount_factor = eligibility.discount_factor
            discounted_value = (adjusted_balance * discount_factor).quantize(
                TWO_PLACES, rounding=ROUND_HALF_UP,
            )

            da = DiscountedAccount(
                account=acct,
                eligibility=eligibility,
                raw_balance=acct.current_balance,
                ownership_adjusted_balance=adjusted_balance,
                seasoned_balance=seasoned,
                discount_factor=discount_factor,
                discounted_value=discounted_value,
            )
            discounted_accounts.append(da)

            total_eligible += adjusted_balance
            total_discounted += discounted_value

            # Categorize
            if acct.account_type in CASH_EQUIVALENT_TYPES:
                by_category["cash_equivalents"] += discounted_value
            elif acct.account_type in MARKETABLE_SECURITIES_TYPES:
                by_category["marketable_securities"] += discounted_value
            elif acct.account_type in RETIREMENT_ACCOUNT_TYPES:
                by_category["retirement"] += discounted_value

            all_warnings.extend(eligibility.warnings)

        return DiscountedAssets(
            accounts=discounted_accounts,
            total_raw_balance=total_raw.quantize(TWO_PLACES),
            total_eligible_balance=total_eligible.quantize(TWO_PLACES),
            total_discounted_value=total_discounted.quantize(TWO_PLACES),
            ineligible_accounts=ineligible,
            warnings=all_warnings,
            by_category={k: v.quantize(TWO_PLACES) for k, v in by_category.items()},
        )

    # =========================================================================
    # 4. SUSTAINABILITY ANALYSIS
    # =========================================================================

    def calculate_sustainability(
        self,
        eligible_assets: Decimal,
        monthly_income_needed: Decimal,
        loan_term_months: int,
    ) -> SustainabilityResult:
        """
        Analyze whether assets will sustain the required monthly income
        through the full loan term.

        Uses three growth scenarios:
            - Conservative: 0% growth (pure depletion)
            - Moderate: 3% annual growth (balanced portfolio)
            - Aggressive: 6% annual growth (equity-heavy portfolio)

        Args:
            eligible_assets: Total discounted eligible assets.
            monthly_income_needed: Required monthly withdrawal.
            loan_term_months: Loan term in months.

        Returns:
            SustainabilityResult with projections and rating.
        """
        recommendations: List[str] = []

        if monthly_income_needed <= ZERO or eligible_assets <= ZERO:
            return SustainabilityResult(
                rating=SustainabilityRating.INSUFFICIENT,
                total_eligible_assets=eligible_assets,
                monthly_depletion_income=monthly_income_needed,
                loan_term_months=loan_term_months,
                total_draw_over_term=ZERO,
                remaining_assets_at_term=ZERO,
                monthly_draw_rate_pct=ZERO,
                annual_draw_rate_pct=ZERO,
                years_assets_will_last=ZERO,
                conservative_years=ZERO,
                moderate_years=ZERO,
                aggressive_years=ZERO,
                recommendations=[
                    "Insufficient assets or zero income requirement."
                ],
            )

        total_draw = (monthly_income_needed * loan_term_months).quantize(TWO_PLACES)
        remaining = (eligible_assets - total_draw).quantize(TWO_PLACES)

        # Monthly and annual draw rates
        monthly_rate = (
            (monthly_income_needed / eligible_assets) * 100
        ).quantize(FOUR_PLACES, rounding=ROUND_HALF_UP)
        annual_rate = (monthly_rate * 12).quantize(FOUR_PLACES, rounding=ROUND_HALF_UP)

        # Years assets will last at each growth rate
        conservative_years = self._years_to_depletion(
            eligible_assets, monthly_income_needed, Decimal("0.00"),
        )
        moderate_years = self._years_to_depletion(
            eligible_assets, monthly_income_needed, Decimal("0.03"),
        )
        aggressive_years = self._years_to_depletion(
            eligible_assets, monthly_income_needed, Decimal("0.06"),
        )

        loan_term_years = Decimal(str(loan_term_months)) / Decimal("12")

        # Determine rating
        if conservative_years >= loan_term_years:
            rating = SustainabilityRating.STRONG
        elif moderate_years >= loan_term_years:
            rating = SustainabilityRating.ADEQUATE
            recommendations.append(
                "Assets require moderate portfolio growth (~3% annual) to last "
                "through the full loan term. Consider more conservative projections."
            )
        elif aggressive_years >= loan_term_years:
            rating = SustainabilityRating.MARGINAL
            recommendations.append(
                "Assets require aggressive portfolio growth (~6% annual) to last "
                "through the loan term. High risk of asset exhaustion."
            )
        else:
            rating = SustainabilityRating.INSUFFICIENT
            recommendations.append(
                f"Assets are projected to be exhausted before loan maturity. "
                f"Conservative estimate: {conservative_years:.1f} years vs "
                f"{loan_term_years:.1f} year term."
            )

        # Draw rate warnings
        if monthly_rate > SUSTAINABILITY_CRITICAL_DRAW_PCT:
            recommendations.append(
                f"Monthly draw rate of {monthly_rate:.2f}% is very high. "
                f"Consider shorter loan term or additional income sources."
            )
        elif monthly_rate > SUSTAINABILITY_WARN_DRAW_PCT:
            recommendations.append(
                f"Monthly draw rate of {monthly_rate:.2f}% exceeds conservative "
                f"withdrawal guidelines."
            )

        return SustainabilityResult(
            rating=rating,
            total_eligible_assets=eligible_assets,
            monthly_depletion_income=monthly_income_needed,
            loan_term_months=loan_term_months,
            total_draw_over_term=total_draw,
            remaining_assets_at_term=remaining,
            monthly_draw_rate_pct=monthly_rate,
            annual_draw_rate_pct=annual_rate,
            years_assets_will_last=conservative_years,
            conservative_years=conservative_years,
            moderate_years=moderate_years,
            aggressive_years=aggressive_years,
            recommendations=recommendations,
        )

    # =========================================================================
    # 5. AGENCY-SPECIFIC RULES
    # =========================================================================

    def get_agency_specific_rules(
        self,
        agency: AgencyType,
        borrower_age: Optional[Decimal] = None,
    ) -> AgencyRules:
        """
        Return the full set of agency-specific rules for asset depletion.

        Args:
            agency: Agency/investor type.
            borrower_age: Borrower's age (affects retirement eligibility).

        Returns:
            AgencyRules with complete rule set.
        """
        if agency == AgencyType.FANNIE_MAE:
            # Fannie Mae B3-3.1-09
            eligible_types = list(
                CASH_EQUIVALENT_TYPES | MARKETABLE_SECURITIES_TYPES | RETIREMENT_ACCOUNT_TYPES
            )
            retirement_eligible = True
            retirement_min = None

            # Build discount map
            age = borrower_age or Decimal("0")
            discount_map: Dict[str, Decimal] = {}
            for acct_type in CASH_EQUIVALENT_TYPES:
                discount_map[acct_type.value] = Decimal("1.00")
            for acct_type in MARKETABLE_SECURITIES_TYPES:
                discount_map[acct_type.value] = Decimal("0.70")
            for acct_type in RETIREMENT_ACCOUNT_TYPES:
                discount_map[acct_type.value] = (
                    Decimal("0.70") if age >= IRA_PENALTY_FREE_AGE else Decimal("0.60")
                )

            return AgencyRules(
                agency=AgencyType.FANNIE_MAE,
                max_ltv=None,  # No LTV restriction specific to asset depletion
                max_amortization_months=None,  # Uses full loan term
                retirement_accounts_eligible=retirement_eligible,
                retirement_min_age=retirement_min,
                discount_factors=discount_map,
                eligible_account_types=eligible_types,
                additional_requirements=[
                    "Borrower must have sufficient assets to cover down payment, "
                    "closing costs, and reserves in addition to depletion income.",
                    "Assets must be liquid and accessible without restriction.",
                    "60-day seasoning required for account balances.",
                ],
                documentation_requirements=[
                    "2 consecutive months of account statements (or quarterly statement)",
                    "Verification of account ownership",
                    "Large deposit documentation (deposits > 50% of monthly income)",
                    "Retirement account: vesting schedule and withdrawal terms",
                ],
            )

        elif agency == AgencyType.FREDDIE_MAC:
            # Freddie Mac Guide 5306.1
            age = borrower_age or Decimal("0")
            eligible_types = list(CASH_EQUIVALENT_TYPES | MARKETABLE_SECURITIES_TYPES)
            retirement_eligible = age >= FREDDIE_RETIREMENT_MIN_AGE

            if retirement_eligible:
                eligible_types.extend(list(RETIREMENT_ACCOUNT_TYPES))

            discount_map = {}
            for acct_type in CASH_EQUIVALENT_TYPES:
                discount_map[acct_type.value] = Decimal("1.00")
            for acct_type in MARKETABLE_SECURITIES_TYPES:
                discount_map[acct_type.value] = Decimal("0.70")
            if retirement_eligible:
                for acct_type in RETIREMENT_ACCOUNT_TYPES:
                    discount_map[acct_type.value] = Decimal("0.70")

            return AgencyRules(
                agency=AgencyType.FREDDIE_MAC,
                max_ltv=FREDDIE_MAX_LTV,
                max_amortization_months=FREDDIE_MAX_AMORT_MONTHS,
                retirement_accounts_eligible=retirement_eligible,
                retirement_min_age=FREDDIE_RETIREMENT_MIN_AGE,
                discount_factors=discount_map,
                eligible_account_types=eligible_types,
                additional_requirements=[
                    f"Maximum LTV: {FREDDIE_MAX_LTV}%",
                    f"Amortization capped at {FREDDIE_MAX_AMORT_MONTHS} months "
                    f"(not full loan term)",
                    "Retirement accounts only eligible if borrower >= 62",
                    "Primary residence and second home only (no investment properties)",
                ],
                documentation_requirements=[
                    "2 consecutive months of account statements",
                    "Verification of account ownership and access",
                    "Evidence of LTV <= 80%",
                ],
            )

        elif agency == AgencyType.FHA:
            # FHA does not allow asset depletion income
            return AgencyRules(
                agency=AgencyType.FHA,
                max_ltv=None,
                max_amortization_months=None,
                retirement_accounts_eligible=False,
                retirement_min_age=None,
                discount_factors={},
                eligible_account_types=[],
                additional_requirements=[
                    "FHA does not allow asset depletion as qualifying income."
                ],
                documentation_requirements=[],
            )

        elif agency == AgencyType.VA:
            # VA does not allow asset depletion income
            return AgencyRules(
                agency=AgencyType.VA,
                max_ltv=None,
                max_amortization_months=None,
                retirement_accounts_eligible=False,
                retirement_min_age=None,
                discount_factors={},
                eligible_account_types=[],
                additional_requirements=[
                    "VA does not allow asset depletion as qualifying income."
                ],
                documentation_requirements=[],
            )

        else:
            # Non-QM or other: use Fannie Mae as baseline with relaxed rules
            eligible_types = list(
                CASH_EQUIVALENT_TYPES | MARKETABLE_SECURITIES_TYPES | RETIREMENT_ACCOUNT_TYPES
            )
            age = borrower_age or Decimal("0")

            discount_map = {}
            for acct_type in CASH_EQUIVALENT_TYPES:
                discount_map[acct_type.value] = Decimal("1.00")
            for acct_type in MARKETABLE_SECURITIES_TYPES:
                discount_map[acct_type.value] = Decimal("0.70")
            for acct_type in RETIREMENT_ACCOUNT_TYPES:
                discount_map[acct_type.value] = (
                    Decimal("0.70") if age >= IRA_PENALTY_FREE_AGE else Decimal("0.60")
                )

            return AgencyRules(
                agency=AgencyType.NON_QM,
                max_ltv=None,
                max_amortization_months=None,
                retirement_accounts_eligible=True,
                retirement_min_age=None,
                discount_factors=discount_map,
                eligible_account_types=eligible_types,
                additional_requirements=[
                    "Non-QM: asset depletion rules vary by investor. "
                    "Using Fannie Mae methodology as baseline.",
                    "Verify with specific investor overlay requirements.",
                ],
                documentation_requirements=[
                    "2 consecutive months of account statements",
                    "Verification of account ownership",
                    "Check investor-specific documentation requirements",
                ],
            )

    # =========================================================================
    # INTERNAL HELPERS
    # =========================================================================

    def _validate_inputs(
        self,
        accounts: List[AssetAccount],
        borrower_age: Decimal,
        loan_term_months: int,
        down_payment: Decimal,
        closing_costs: Decimal,
    ) -> List[str]:
        """Validate calculation inputs and return list of error messages."""
        errors: List[str] = []

        if not accounts:
            errors.append("NO_ACCOUNTS_PROVIDED")

        if borrower_age <= ZERO:
            errors.append("INVALID_BORROWER_AGE")

        if loan_term_months <= 0:
            errors.append("INVALID_LOAN_TERM")

        if down_payment < ZERO:
            errors.append("NEGATIVE_DOWN_PAYMENT")

        if closing_costs < ZERO:
            errors.append("NEGATIVE_CLOSING_COSTS")

        for i, acct in enumerate(accounts):
            if acct.current_balance < ZERO:
                errors.append(f"NEGATIVE_BALANCE_ACCOUNT_{i}")

        return errors

    async def _verify_loan_org(self, loan_id: int) -> None:
        """Verify loan belongs to this organization."""
        row = self.db.execute(
            text("SELECT organization_id FROM loans WHERE id = :loan_id"),
            {"loan_id": loan_id},
        ).fetchone()

        if row is None:
            from exceptions import LoanNotFoundError
            raise LoanNotFoundError(loan_id)

        self._require_org_match(row.organization_id)

    async def _check_agency_prerequisites(
        self,
        loan_id: int,
        agency: AgencyType,
        rules: AgencyRules,
    ) -> List[str]:
        """Check agency-specific prerequisites from loan data."""
        flags: List[str] = []

        if agency in (AgencyType.FHA, AgencyType.VA):
            flags.append(
                f"ASSET_DEPLETION_NOT_ALLOWED_{agency.value.upper()}"
            )
            return flags

        if agency == AgencyType.FREDDIE_MAC:
            # Check LTV from loan data
            loan_data = self.db.execute(
                text("""
                    SELECT amount, appraised_value, purchase_price
                    FROM loans
                    WHERE id = :loan_id
                """),
                {"loan_id": loan_id},
            ).fetchone()

            if loan_data and loan_data.appraised_value:
                property_value = min(
                    Decimal(str(loan_data.appraised_value or 0)),
                    Decimal(str(loan_data.purchase_price or loan_data.appraised_value or 0)),
                )
                if property_value > ZERO:
                    ltv = (
                        Decimal(str(loan_data.amount or 0)) / property_value * 100
                    ).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
                    if ltv > FREDDIE_MAX_LTV:
                        flags.append(
                            f"FREDDIE_LTV_EXCEEDS_MAX: {ltv}% > {FREDDIE_MAX_LTV}%"
                        )

        return flags

    def _get_discount_factor(
        self,
        account_type: AccountType,
        borrower_age: Decimal,
        agency: AgencyType,
    ) -> Decimal:
        """Look up the discount factor for an account type."""
        if agency == AgencyType.FREDDIE_MAC:
            return FREDDIE_DISCOUNT_FACTORS.get(account_type, ZERO)

        # Fannie Mae (default)
        if account_type in CASH_EQUIVALENT_TYPES:
            return FANNIE_DISCOUNT_FACTORS["cash_equivalents"].get(
                account_type, ZERO,
            )
        elif account_type in MARKETABLE_SECURITIES_TYPES:
            return FANNIE_DISCOUNT_FACTORS["marketable_securities"].get(
                account_type, ZERO,
            )
        elif account_type in RETIREMENT_ACCOUNT_TYPES:
            if borrower_age >= IRA_PENALTY_FREE_AGE:
                return FANNIE_DISCOUNT_FACTORS["retirement_over_59_5"].get(
                    account_type, ZERO,
                )
            else:
                return FANNIE_DISCOUNT_FACTORS["retirement_under_59_5"].get(
                    account_type, ZERO,
                )

        # Trust or other special types: treat as marketable securities
        if account_type == AccountType.TRUST:
            return Decimal("0.70")

        return ZERO

    def _calculate_tax_impact(
        self,
        accounts: List[AssetAccount],
        annual_distribution: Decimal,
        borrower_age: Decimal,
        state_code: Optional[str] = None,
    ) -> TaxImpactAnalysis:
        """
        Estimate tax impact of asset distributions.

        This is an estimation for planning purposes. Actual tax impact depends
        on the borrower's full tax situation (filing status, other income,
        deductions, etc.).
        """
        if annual_distribution <= ZERO:
            return TaxImpactAnalysis(
                annual_distribution_amount=ZERO,
                estimated_federal_tax=ZERO,
                estimated_state_tax=ZERO,
                early_withdrawal_penalty=ZERO,
                total_tax_impact=ZERO,
                effective_tax_rate=ZERO,
                after_tax_annual_income=ZERO,
                after_tax_monthly_income=ZERO,
            )

        # Determine how much comes from taxable vs. tax-free sources
        retirement_balance = ZERO
        roth_balance = ZERO
        taxable_securities_balance = ZERO
        cash_balance = ZERO

        for acct in accounts:
            if acct.account_type in INELIGIBLE_ACCOUNT_TYPES:
                continue
            if acct.account_type in {
                AccountType.IRA_ROTH,
                AccountType.ROTH_401K,
            }:
                roth_balance += acct.current_balance
            elif acct.account_type in RETIREMENT_ACCOUNT_TYPES:
                retirement_balance += acct.current_balance
            elif acct.account_type in MARKETABLE_SECURITIES_TYPES:
                taxable_securities_balance += acct.current_balance
            elif acct.account_type in CASH_EQUIVALENT_TYPES:
                cash_balance += acct.current_balance

        total_eligible = retirement_balance + roth_balance + taxable_securities_balance + cash_balance
        if total_eligible <= ZERO:
            total_eligible = Decimal("1")  # Avoid division by zero

        # Pro-rata allocation of annual distribution across account types
        retirement_pct = retirement_balance / total_eligible
        roth_pct = roth_balance / total_eligible
        securities_pct = taxable_securities_balance / total_eligible

        # Traditional retirement distributions: fully taxable as ordinary income
        taxable_retirement_dist = (annual_distribution * retirement_pct).quantize(TWO_PLACES)

        # Roth distributions: tax-free if qualified (age >= 59.5 and 5-year rule)
        # For estimation, assume qualified if >= 59.5
        roth_dist = (annual_distribution * roth_pct).quantize(TWO_PLACES)
        roth_taxable = ZERO if borrower_age >= IRA_PENALTY_FREE_AGE else roth_dist

        # Securities: only capital gains portion is taxable
        # Assume 50% of securities value is gain (conservative estimate)
        securities_dist = (annual_distribution * securities_pct).quantize(TWO_PLACES)
        securities_taxable = (securities_dist * Decimal("0.50")).quantize(TWO_PLACES)

        # Total taxable amount
        total_taxable = taxable_retirement_dist + roth_taxable + securities_taxable

        # Federal tax estimation using simplified brackets
        federal_tax = self._estimate_federal_tax(total_taxable)

        # State tax estimation (rough approximation)
        state_tax_rate = self._get_state_tax_rate(state_code)
        state_tax = (total_taxable * state_tax_rate).quantize(TWO_PLACES)

        # Early withdrawal penalty (10% on traditional retirement if < 59.5)
        early_penalty = ZERO
        if borrower_age < IRA_PENALTY_FREE_AGE:
            early_penalty = (
                taxable_retirement_dist * EARLY_WITHDRAWAL_PENALTY_RATE
            ).quantize(TWO_PLACES)

        total_tax = federal_tax + state_tax + early_penalty
        effective_rate = (
            (total_tax / annual_distribution * 100).quantize(TWO_PLACES)
            if annual_distribution > ZERO else ZERO
        )
        after_tax_annual = (annual_distribution - total_tax).quantize(TWO_PLACES)
        after_tax_monthly = (after_tax_annual / 12).quantize(TWO_PLACES)

        # RMD analysis
        rmd_amount = None
        rmd_notes: List[str] = []
        int_age = int(borrower_age)

        if int_age >= RMD_START_AGE and retirement_balance > ZERO:
            divisor = RMD_DIVISOR_TABLE.get(int_age)
            if divisor and divisor > ZERO:
                rmd_amount = (retirement_balance / divisor).quantize(TWO_PLACES)
                annual_retirement_dist = taxable_retirement_dist
                if rmd_amount > annual_retirement_dist:
                    rmd_notes.append(
                        f"RMD ({rmd_amount:,.2f}/yr) exceeds planned retirement "
                        f"distribution ({annual_retirement_dist:,.2f}/yr). "
                        f"The higher RMD amount must be taken regardless."
                    )
                else:
                    rmd_notes.append(
                        f"Planned retirement distribution ({annual_retirement_dist:,.2f}/yr) "
                        f"satisfies RMD requirement ({rmd_amount:,.2f}/yr)."
                    )
        elif int_age >= RMD_START_AGE - 3 and retirement_balance > ZERO:
            rmd_notes.append(
                f"Borrower will reach RMD age ({RMD_START_AGE}) within 3 years. "
                f"Plan for required minimum distributions."
            )

        # Capital gains notes
        cg_notes: List[str] = []
        if taxable_securities_balance > ZERO:
            cg_notes.append(
                "Securities distributions may trigger capital gains tax. "
                "Actual tax depends on holding period (short-term vs long-term) "
                "and cost basis."
            )

        return TaxImpactAnalysis(
            annual_distribution_amount=annual_distribution,
            estimated_federal_tax=federal_tax,
            estimated_state_tax=state_tax,
            early_withdrawal_penalty=early_penalty,
            total_tax_impact=total_tax,
            effective_tax_rate=effective_rate,
            after_tax_annual_income=after_tax_annual,
            after_tax_monthly_income=after_tax_monthly,
            rmd_amount=rmd_amount,
            rmd_coordination_notes=rmd_notes,
            capital_gains_notes=cg_notes,
        )

    def _estimate_federal_tax(self, taxable_income: Decimal) -> Decimal:
        """Estimate federal income tax from simplified 2024/2025 brackets."""
        if taxable_income <= ZERO:
            return ZERO

        tax = ZERO
        previous_bracket_max = ZERO

        for bracket_max, rate in FEDERAL_TAX_BRACKETS:
            if taxable_income <= previous_bracket_max:
                break
            taxable_in_bracket = min(
                taxable_income, bracket_max
            ) - previous_bracket_max
            if taxable_in_bracket > ZERO:
                tax += (taxable_in_bracket * rate).quantize(TWO_PLACES)
            previous_bracket_max = bracket_max

        return tax.quantize(TWO_PLACES, rounding=ROUND_HALF_UP)

    def _get_state_tax_rate(self, state_code: Optional[str]) -> Decimal:
        """Return approximate state income tax rate for estimation."""
        if not state_code:
            return Decimal("0.05")  # Default 5% estimate

        # States with no income tax
        no_tax_states = {"AK", "FL", "NV", "NH", "SD", "TN", "TX", "WA", "WY"}
        if state_code.upper() in no_tax_states:
            return ZERO

        # High-tax states (approximate top marginal rates)
        high_tax_map: Dict[str, Decimal] = {
            "CA": Decimal("0.093"),
            "HI": Decimal("0.11"),
            "NJ": Decimal("0.1075"),
            "OR": Decimal("0.099"),
            "MN": Decimal("0.0985"),
            "NY": Decimal("0.0882"),
            "VT": Decimal("0.0875"),
            "IA": Decimal("0.06"),
            "DC": Decimal("0.0895"),
            "WI": Decimal("0.0765"),
        }
        if state_code.upper() in high_tax_map:
            return high_tax_map[state_code.upper()]

        # Default moderate state tax rate
        return Decimal("0.05")

    def _check_double_counting(
        self,
        accounts: List[AssetAccount],
        other_income_monthly: Decimal,
        loan_id: int,
    ) -> Dict[str, Any]:
        """
        Check for potential double-counting between asset depletion and
        traditional retirement income sources.
        """
        result: Dict[str, Any] = {"flags": [], "warnings": []}

        if other_income_monthly <= ZERO:
            return result

        # Check if any retirement accounts are included in asset depletion
        has_retirement = any(
            acct.account_type in RETIREMENT_ACCOUNT_TYPES
            for acct in accounts
            if acct.account_type not in INELIGIBLE_ACCOUNT_TYPES
        )

        if has_retirement:
            # Check existing income sources for retirement/pension/social security
            existing_sources = self.db.execute(
                text("""
                    SELECT DISTINCT is2.source_type
                    FROM income_sources is2
                    JOIN income_calculations ic ON ic.id = is2.calculation_id
                    WHERE ic.loan_id = :loan_id
                      AND is2.source_type IN ('pension', 'social_security', 'investment')
                      AND ic.status NOT IN ('rejected')
                    ORDER BY is2.source_type
                """),
                {"loan_id": loan_id},
            ).fetchall()

            retirement_income_types = {row.source_type for row in existing_sources}

            if "pension" in retirement_income_types:
                result["warnings"].append(
                    "DOUBLE_COUNT_RISK: Pension income is already counted as "
                    "traditional income. If pension is funded from a retirement "
                    "account included in asset depletion, the same assets may "
                    "be counted twice."
                )

            if "social_security" in retirement_income_types:
                # SS is not funded from borrower's accounts, so no double-count
                pass

            if "investment" in retirement_income_types:
                result["warnings"].append(
                    "DOUBLE_COUNT_RISK: Investment income is already counted. "
                    "Verify that investment accounts used for asset depletion "
                    "are not the same accounts generating counted investment income."
                )

        return result

    def _build_documentation_requirements(
        self,
        accounts: List[AssetAccount],
        eligibility_results: List[EligibilityResult],
    ) -> List[str]:
        """Aggregate documentation requirements from all accounts."""
        requirements: List[str] = []
        seen: set = set()

        for er in eligibility_results:
            for req in er.documentation_requirements:
                if req not in seen:
                    requirements.append(req)
                    seen.add(req)

        # Check for accounts with insufficient statements
        for acct in accounts:
            if acct.months_of_statements < 2:
                req = (
                    f"{acct.institution_name} ({acct.account_type.value}): "
                    f"Need 2 consecutive monthly statements "
                    f"(have {acct.months_of_statements})"
                )
                if req not in seen:
                    requirements.append(req)
                    seen.add(req)

            # Large deposit documentation
            if acct.large_deposits:
                for dep in acct.large_deposits:
                    req = (
                        f"Source documentation for {dep.get('amount', '?'):,} "
                        f"deposit at {acct.institution_name} "
                        f"on {dep.get('date', 'unknown')}"
                    )
                    if req not in seen:
                        requirements.append(req)
                        seen.add(req)

        return requirements

    def _calculate_confidence(
        self,
        accounts: List[AssetAccount],
        eligibility_results: List[EligibilityResult],
        discounted: DiscountedAssets,
        sustainability: SustainabilityResult,
    ) -> int:
        """Calculate confidence score (0-100) for the calculation."""
        score = 100

        # Deduct for missing documentation
        accounts_with_insufficient_docs = sum(
            1 for acct in accounts if acct.months_of_statements < 2
        )
        score -= accounts_with_insufficient_docs * 10

        # Deduct for missing 60-day averages
        accounts_without_avg = sum(
            1 for acct in accounts
            if acct.sixty_day_average_balance is None
            and acct.account_type not in INELIGIBLE_ACCOUNT_TYPES
        )
        score -= accounts_without_avg * 5

        # Deduct for ineligible accounts (they might indicate data quality issues)
        ineligible_count = len(discounted.ineligible_accounts)
        if ineligible_count > 0:
            score -= min(ineligible_count * 3, 15)

        # Deduct for sustainability concerns
        if sustainability.rating == SustainabilityRating.MARGINAL:
            score -= 10
        elif sustainability.rating == SustainabilityRating.INSUFFICIENT:
            score -= 20

        # Deduct for large deposits that need sourcing
        large_deposit_count = sum(
            len(acct.large_deposits or []) for acct in accounts
        )
        score -= min(large_deposit_count * 5, 15)

        # Deduct for eligibility warnings
        total_warnings = sum(len(er.warnings) for er in eligibility_results)
        score -= min(total_warnings * 2, 10)

        return max(0, min(100, score))

    def _years_to_depletion(
        self,
        principal: Decimal,
        monthly_withdrawal: Decimal,
        annual_growth_rate: Decimal,
    ) -> Decimal:
        """
        Calculate how many years assets will last given monthly withdrawals
        and an assumed annual growth rate.

        Uses iterative monthly simulation for accuracy with compounding.
        """
        if monthly_withdrawal <= ZERO or principal <= ZERO:
            return Decimal("0")

        monthly_growth = (
            (Decimal("1") + annual_growth_rate) ** (Decimal("1") / Decimal("12"))
        ) - Decimal("1")

        balance = principal
        months = 0
        max_months = 1200  # 100-year cap

        while balance > ZERO and months < max_months:
            # Apply monthly growth
            balance = balance * (Decimal("1") + monthly_growth)
            # Withdraw
            balance -= monthly_withdrawal
            months += 1

        years = Decimal(str(months)) / Decimal("12")
        return years.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)

    def _generate_tasks(
        self,
        loan_id: int,
        borrower_id: Optional[int],
        flags: List[str],
        recommendations: List[str],
        doc_requirements: List[str],
        accounts: List[AssetAccount],
    ) -> List[Dict[str, Any]]:
        """Generate LO verification tasks from analysis results."""
        tasks: List[Dict[str, Any]] = []

        # Missing documentation tasks
        for acct in accounts:
            if acct.months_of_statements < 2:
                tasks.append({
                    "task_type": "review_large_deposit",
                    "title": (
                        f"Obtain 2 months statements: {acct.institution_name} "
                        f"({acct.account_type.value})"
                    ),
                    "description": (
                        f"Asset depletion requires 2 consecutive monthly statements "
                        f"for {acct.institution_name}. Currently have "
                        f"{acct.months_of_statements} month(s)."
                    ),
                    "priority": "high",
                    "loan_id": loan_id,
                    "borrower_id": borrower_id,
                })

            # Large deposit tasks
            if acct.large_deposits:
                for dep in acct.large_deposits:
                    tasks.append({
                        "task_type": "review_large_deposit",
                        "title": (
                            f"Source large deposit: "
                            f"${dep.get('amount', 0):,.2f} at {acct.institution_name}"
                        ),
                        "description": (
                            f"Large deposit of ${dep.get('amount', 0):,.2f} on "
                            f"{dep.get('date', 'unknown')} requires source "
                            f"documentation per agency guidelines."
                        ),
                        "priority": "high",
                        "loan_id": loan_id,
                        "borrower_id": borrower_id,
                    })

        # Flag-driven tasks
        if "MARGINAL_SUSTAINABILITY" in flags:
            tasks.append({
                "task_type": "manual_override_needed",
                "title": "Review marginal asset sustainability",
                "description": (
                    "Asset depletion sustainability rated as marginal. "
                    "Assets may not last through the full loan term without "
                    "favorable market conditions."
                ),
                "priority": "medium",
                "loan_id": loan_id,
                "borrower_id": borrower_id,
            })

        if "INSUFFICIENT_SUSTAINABILITY" in flags:
            tasks.append({
                "task_type": "manual_override_needed",
                "title": "Asset depletion sustainability insufficient",
                "description": (
                    "Assets are projected to be exhausted before loan maturity. "
                    "Review with borrower for additional assets or alternative "
                    "qualification strategies."
                ),
                "priority": "critical",
                "loan_id": loan_id,
                "borrower_id": borrower_id,
            })

        for flag in flags:
            if flag.startswith("DOUBLE_COUNT_RISK"):
                tasks.append({
                    "task_type": "manual_override_needed",
                    "title": "Review potential double-counted income",
                    "description": flag,
                    "priority": "high",
                    "loan_id": loan_id,
                    "borrower_id": borrower_id,
                })
                break  # One task for all double-count warnings

        if any(f.startswith("FREDDIE_LTV_EXCEEDS_MAX") for f in flags):
            tasks.append({
                "task_type": "manual_override_needed",
                "title": "Freddie Mac LTV exceeds 80% maximum for asset depletion",
                "description": (
                    "Freddie Mac Guide 5306.1 requires LTV <= 80% for asset "
                    "depletion qualification. Current LTV exceeds this limit."
                ),
                "priority": "critical",
                "loan_id": loan_id,
                "borrower_id": borrower_id,
            })

        return tasks

    async def _save_calculation(
        self,
        result: AssetDepletionResult,
        borrower_id: Optional[int],
        duration_ms: int,
    ) -> Optional[int]:
        """Persist asset depletion calculation to income_calculations and income_sources."""
        try:
            status = "needs_review" if result.flags else "completed"

            calc_row = self.db.execute(
                text("""
                    INSERT INTO income_calculations (
                        organization_id, loan_id, borrower_id,
                        calculation_type, status,
                        total_qualifying_monthly_income,
                        total_qualifying_annual_income,
                        calculation_method,
                        ai_confidence_score,
                        ai_flags, ai_recommendations,
                        calculation_duration_ms,
                        source_documents,
                        created_at, updated_at
                    ) VALUES (
                        :org_id, :loan_id, :borrower_id,
                        :calc_type, :status,
                        :total_monthly, :total_annual,
                        :method,
                        :confidence,
                        :flags, :recommendations,
                        :duration,
                        :source_docs,
                        :now, :now
                    )
                    RETURNING id
                """),
                {
                    "org_id": self.org_id,
                    "loan_id": result.loan_id,
                    "borrower_id": borrower_id,
                    "calc_type": "initial",
                    "status": status,
                    "total_monthly": float(result.monthly_qualifying_income),
                    "total_annual": float(result.annual_qualifying_income),
                    "method": "asset_depletion",
                    "confidence": result.confidence,
                    "flags": json.dumps(result.flags),
                    "recommendations": json.dumps(result.recommendations),
                    "duration": duration_ms,
                    "source_docs": json.dumps(
                        list({
                            did
                            for acct in result.discounted_assets.accounts
                            for did in (acct.account.document_ids or [])
                        })
                    ),
                    "now": datetime.now(timezone.utc),
                },
            )
            calc_id = calc_row.fetchone()[0]

            # Save as income source of type INVESTMENT (asset depletion)
            self.db.execute(
                text("""
                    INSERT INTO income_sources (
                        calculation_id, borrower_id,
                        source_type,
                        employer_name,
                        base_monthly_income,
                        total_monthly_income, total_annual_income,
                        trending_direction,
                        verification_status,
                        ai_confidence, ai_notes,
                        source_document_ids,
                        created_at, updated_at
                    ) VALUES (
                        :calc_id, :borrower_id,
                        :source_type,
                        :source_name,
                        :base_monthly,
                        :total_monthly, :total_annual,
                        :trending,
                        :verification,
                        :confidence, :notes,
                        :doc_ids,
                        :now, :now
                    )
                """),
                {
                    "calc_id": calc_id,
                    "borrower_id": borrower_id,
                    "source_type": "investment",
                    "source_name": "Asset Depletion Income",
                    "base_monthly": float(result.monthly_qualifying_income),
                    "total_monthly": float(result.monthly_qualifying_income),
                    "total_annual": float(result.annual_qualifying_income),
                    "trending": "stable",
                    "verification": "unverified",
                    "confidence": result.confidence,
                    "notes": json.dumps({
                        "method": "asset_depletion",
                        "agency": result.agency.value,
                        "total_eligible_assets": float(result.total_eligible_assets),
                        "total_discounted_assets": float(result.total_discounted_assets),
                        "net_eligible_assets": float(result.net_eligible_assets),
                        "effective_amort_months": result.effective_amort_months,
                        "sustainability_rating": result.sustainability.rating.value,
                        "tax_impact_effective_rate": float(result.tax_impact.effective_tax_rate),
                    }),
                    "doc_ids": json.dumps(
                        list({
                            did
                            for acct in result.discounted_assets.accounts
                            for did in (acct.account.document_ids or [])
                        })
                    ),
                    "now": datetime.now(timezone.utc),
                },
            )

            # Save verification tasks
            for task in result.tasks_to_create:
                self.db.execute(
                    text("""
                        INSERT INTO income_verification_tasks (
                            calculation_id, loan_id, organization_id,
                            task_type, title, description,
                            priority, status,
                            created_at, updated_at
                        ) VALUES (
                            :calc_id, :loan_id, :org_id,
                            :task_type, :title, :description,
                            :priority, :status,
                            :now, :now
                        )
                    """),
                    {
                        "calc_id": calc_id,
                        "loan_id": result.loan_id,
                        "org_id": self.org_id,
                        "task_type": task.get("task_type", "manual_override_needed"),
                        "title": task["title"],
                        "description": task.get("description", ""),
                        "priority": task.get("priority", "medium"),
                        "status": "open",
                        "now": datetime.now(timezone.utc),
                    },
                )

            self.db.commit()

            logger.info(
                f"Saved asset depletion calculation {calc_id} for loan "
                f"{result.loan_id} org {self.org_id}: "
                f"confidence={result.confidence}"
            )
            return calc_id

        except Exception as e:
            logger.exception(
                f"Failed to save asset depletion calculation for loan "
                f"{result.loan_id}: {e}"
            )
            self.db.rollback()
            return None


# =============================================================================
# FACTORY FUNCTION
# =============================================================================

def get_asset_depletion_service(
    db: Session,
    org_id: int,
    user_id: Optional[int] = None,
) -> AssetDepletionService:
    """
    Factory function returning an AssetDepletionService for the given session.

    Args:
        db: SQLAlchemy database session.
        org_id: Organization ID for tenant isolation.
        user_id: Authenticated user ID (optional).

    Returns:
        AssetDepletionService instance.
    """
    return AssetDepletionService(db=db, org_id=org_id, user_id=user_id)
