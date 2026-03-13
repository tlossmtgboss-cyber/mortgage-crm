"""
Retirement Income Validation Service for Mortgage Underwriting

Validates and calculates qualifying retirement income per Fannie Mae Selling
Guide (B3-3.1-09), FHA Handbook 4000.1, and VA Lender's Handbook Chapter 4.

Retirement income types handled:
    1. Social Security (SSA-1099)
    2. Pension / Annuity (1099-R, defined-benefit plans)
    3. IRA / 401(k) distributions (1099-R)
    4. Military retirement pay
    5. Disability income (SSA / private / VA)
    6. VA disability compensation

Key compliance areas:
    - 3-year continuance documentation
    - Non-taxable income gross-up (25% per Fannie Mae B3-3.1-01)
    - Asset depletion / distribution sustainability (Fannie Mae B3-4.3-09)
    - Age-based validation (early withdrawal penalties, RMD compliance)
    - COLA adjustments for Social Security

Integrates with:
    - smart_documents / smart_document_extractions for document data
    - income_calculations / income_sources for result persistence
    - income_verification_tasks for LO follow-up items

Usage:
    from services.smart_docs.income.retirement_income_service import (
        get_retirement_income_service,
        RetirementIncomeService,
    )

    service = get_retirement_income_service(db)
    result = await service.calculate_retirement_income(
        org_id=org_id,
        borrower_id=borrower_id,
        income_sources=[...],
    )
"""

import json
import logging
import time
from datetime import datetime, timezone, date, timedelta
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, field

from sqlalchemy.orm import Session
from sqlalchemy import text

logger = logging.getLogger(__name__)


# =============================================================================
# CONSTANTS
# =============================================================================

ZERO = Decimal("0.00")
TWO_PLACES = Decimal("0.01")
FOUR_PLACES = Decimal("0.0001")

# Fannie Mae B3-3.1-01: non-taxable income may be grossed up by 25%
DEFAULT_GROSS_UP_PCT = Decimal("25.00")
MAX_GROSS_UP_PCT = Decimal("25.00")

# Social Security tax thresholds (2025/2026 IRS rules)
# Single filers: up to 85% of SS may be taxable above combined income $34,000
SS_SINGLE_THRESHOLD_LOW = Decimal("25000.00")
SS_SINGLE_THRESHOLD_HIGH = Decimal("34000.00")
SS_JOINT_THRESHOLD_LOW = Decimal("32000.00")
SS_JOINT_THRESHOLD_HIGH = Decimal("44000.00")
SS_MAX_TAXABLE_PCT = Decimal("85.00")

# Asset depletion: Fannie Mae B3-4.3-09
# 70% of stocks/bonds/mutual funds (market risk discount)
MARKET_RISK_DISCOUNT = Decimal("0.70")
# 100% of cash equivalents (checking, savings, CDs, money market)
CASH_EQUIVALENT_FACTOR = Decimal("1.00")

# Continuance requirement: minimum 3 years
CONTINUANCE_YEARS_REQUIRED = 3
CONTINUANCE_MONTHS_REQUIRED = CONTINUANCE_YEARS_REQUIRED * 12

# Age thresholds
RMD_AGE = 73  # SECURE 2.0 Act: RMD age is 73 starting 2023, 75 starting 2033
EARLY_WITHDRAWAL_AGE = 59  # 59.5 rounded down for date comparison
EARLY_WITHDRAWAL_PENALTY_PCT = Decimal("10.00")
SOCIAL_SECURITY_EARLY_AGE = 62
SOCIAL_SECURITY_FULL_AGE = 67  # For those born 1960+

# 2025 COLA for Social Security (applied automatically by SSA)
SS_COLA_2025_PCT = Decimal("2.5")

# Months per year
MONTHS_PER_YEAR = 12

# Retirement document types (match DocType enum in smart_docs models)
RETIREMENT_DOC_TYPES = (
    "SSA_1099",
    "1099_R",
    "AWARD_LETTER",
    "BENEFIT_STATEMENT",
    "VA_AWARD_LETTER",
    "PENSION_STATEMENT",
    "RETIREMENT_ACCOUNT_STATEMENT",
    "DISABILITY_AWARD",
)


# =============================================================================
# ENUMS
# =============================================================================

class RetirementIncomeType(str, Enum):
    """Types of retirement income recognized for mortgage qualification."""
    SOCIAL_SECURITY = "social_security"
    PENSION = "pension"
    ANNUITY = "annuity"
    IRA_DISTRIBUTION = "ira_distribution"
    FOUR_OH_ONE_K = "401k_distribution"
    MILITARY_RETIREMENT = "military_retirement"
    DISABILITY_SSA = "disability_ssa"
    DISABILITY_PRIVATE = "disability_private"
    VA_DISABILITY = "va_disability"
    ASSET_DEPLETION = "asset_depletion"


class ContinuanceStatus(str, Enum):
    """Continuance determination for income sources."""
    PERMANENT = "permanent"
    LIKELY_TO_CONTINUE = "likely_to_continue"
    EXPIRING = "expiring"
    EXPIRED = "expired"
    UNKNOWN = "unknown"


class AccountType(str, Enum):
    """Retirement/investment account types for asset depletion analysis."""
    CHECKING = "checking"
    SAVINGS = "savings"
    MONEY_MARKET = "money_market"
    CD = "cd"
    IRA_TRADITIONAL = "ira_traditional"
    IRA_ROTH = "roth_ira"
    FOUR_OH_ONE_K = "401k"
    FOUR_OH_THREE_B = "403b"
    BROKERAGE = "brokerage"
    MUTUAL_FUND = "mutual_fund"
    STOCK = "stock"
    BOND = "bond"


class FlagSeverity(str, Enum):
    """Severity levels for validation flags."""
    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


# Cash-equivalent account types that get 100% credit
CASH_EQUIVALENT_TYPES = {
    AccountType.CHECKING,
    AccountType.SAVINGS,
    AccountType.MONEY_MARKET,
    AccountType.CD,
}

# Market-risk account types that get 70% credit
MARKET_RISK_TYPES = {
    AccountType.IRA_TRADITIONAL,
    AccountType.IRA_ROTH,
    AccountType.FOUR_OH_ONE_K,
    AccountType.FOUR_OH_THREE_B,
    AccountType.BROKERAGE,
    AccountType.MUTUAL_FUND,
    AccountType.STOCK,
    AccountType.BOND,
}


# =============================================================================
# DATA CLASSES — INPUTS
# =============================================================================

@dataclass
class RetirementIncomeSource:
    """Single retirement income source provided for validation."""
    income_type: RetirementIncomeType
    monthly_amount: Decimal
    annual_amount: Optional[Decimal] = None
    payer_name: Optional[str] = None

    # Documentation references
    award_letter_on_file: bool = False
    form_1099r_on_file: bool = False
    ssa_1099_on_file: bool = False
    benefit_statement_on_file: bool = False
    account_statements_on_file: bool = False
    source_doc_ids: List[int] = field(default_factory=list)

    # Continuance info
    start_date: Optional[date] = None
    expiration_date: Optional[date] = None
    is_permanent: bool = False
    plan_type: Optional[str] = None  # "defined_benefit", "defined_contribution"

    # Tax status
    is_non_taxable: bool = False
    is_partially_taxable: bool = False
    taxable_percentage: Optional[Decimal] = None

    # Borrower age context
    borrower_date_of_birth: Optional[date] = None

    # For asset depletion analysis
    account_type: Optional[AccountType] = None
    account_balance: Optional[Decimal] = None


@dataclass
class RetirementAccount:
    """A single financial account for asset depletion analysis."""
    account_type: AccountType
    institution_name: Optional[str] = None
    account_number_last4: Optional[str] = None
    current_balance: Decimal = ZERO
    is_retirement_account: bool = False
    is_vested: bool = True
    vesting_percentage: Decimal = Decimal("100.00")
    source_doc_ids: List[int] = field(default_factory=list)


# =============================================================================
# DATA CLASSES — OUTPUTS
# =============================================================================

@dataclass
class ValidationFlag:
    """A single validation issue or informational note."""
    code: str
    severity: FlagSeverity
    message: str
    field: Optional[str] = None


@dataclass
class DocRequirement:
    """A single documentation requirement."""
    doc_type: str
    description: str
    required: bool = True
    years_needed: int = 0
    notes: str = ""


@dataclass
class ContinuanceResult:
    """Result of continuance validation for a single income source."""
    income_type: RetirementIncomeType
    status: ContinuanceStatus
    documented: bool = False
    remaining_months: Optional[int] = None
    expiration_date: Optional[date] = None
    flags: List[ValidationFlag] = field(default_factory=list)
    notes: str = ""


@dataclass
class GrossUpResult:
    """Result of non-taxable income gross-up calculation."""
    original_monthly: Decimal = ZERO
    gross_up_percentage: Decimal = ZERO
    gross_up_amount: Decimal = ZERO
    grossed_up_monthly: Decimal = ZERO
    tax_exempt_type: str = ""
    calculation_detail: str = ""
    flags: List[ValidationFlag] = field(default_factory=list)


@dataclass
class DepletionAccountResult:
    """Analysis of a single account for asset depletion."""
    account_type: AccountType
    institution_name: Optional[str]
    raw_balance: Decimal = ZERO
    discount_factor: Decimal = ZERO
    eligible_balance: Decimal = ZERO
    is_cash_equivalent: bool = False
    notes: str = ""


@dataclass
class DepletionResult:
    """Result of asset depletion / distribution sustainability analysis."""
    total_eligible_assets: Decimal = ZERO
    down_payment: Decimal = ZERO
    closing_costs: Decimal = ZERO
    net_eligible_assets: Decimal = ZERO
    loan_term_months: int = 360
    monthly_income_from_depletion: Decimal = ZERO
    annual_income_from_depletion: Decimal = ZERO
    months_of_income_remaining: int = 0
    is_sustainable: bool = False
    accounts: List[DepletionAccountResult] = field(default_factory=list)
    flags: List[ValidationFlag] = field(default_factory=list)
    calculation_method: str = "fannie_mae_b3_4_3_09"


@dataclass
class RetirementIncomeSourceResult:
    """Calculated qualifying income from a single retirement source."""
    income_type: RetirementIncomeType
    payer_name: Optional[str]
    raw_monthly: Decimal = ZERO
    gross_up_applied: bool = False
    gross_up_result: Optional[GrossUpResult] = None
    qualifying_monthly: Decimal = ZERO
    qualifying_annual: Decimal = ZERO
    continuance: Optional[ContinuanceResult] = None
    is_eligible: bool = True
    ineligible_reason: Optional[str] = None
    confidence: int = 0
    source_doc_ids: List[int] = field(default_factory=list)
    flags: List[ValidationFlag] = field(default_factory=list)
    documentation_status: str = "incomplete"  # complete, incomplete, missing
    notes: str = ""


@dataclass
class RetirementIncomeResult:
    """Complete retirement income validation result."""
    org_id: str
    borrower_id: int
    loan_id: Optional[int] = None
    sources: List[RetirementIncomeSourceResult] = field(default_factory=list)
    depletion_result: Optional[DepletionResult] = None
    total_qualifying_monthly: Decimal = ZERO
    total_qualifying_annual: Decimal = ZERO
    total_before_gross_up: Decimal = ZERO
    total_gross_up_amount: Decimal = ZERO
    has_employment_combo: bool = False
    employment_income_monthly: Decimal = ZERO
    combined_monthly_income: Decimal = ZERO
    confidence: int = 0
    flags: List[ValidationFlag] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)
    tasks_to_create: List[Dict] = field(default_factory=list)
    doc_requirements: List[DocRequirement] = field(default_factory=list)
    success: bool = True
    error: Optional[str] = None
    calculated_at: Optional[datetime] = None


# =============================================================================
# SERVICE
# =============================================================================

class RetirementIncomeService:
    """
    Validates and calculates qualifying retirement income for mortgage
    underwriting per Fannie Mae, FHA, and VA guidelines.

    Key responsibilities:
    - Validate continuance likelihood (3-year requirement)
    - Apply non-taxable income gross-up (up to 25%)
    - Analyze asset depletion sustainability
    - Age-based validation (early withdrawals, RMD)
    - Generate documentation requirements and LO tasks

    All methods enforce org_id tenant isolation.
    """

    def __init__(self, db: Session):
        self.db = db

    # =========================================================================
    # 1. MAIN ENTRY POINT
    # =========================================================================

    async def calculate_retirement_income(
        self,
        org_id: str,
        borrower_id: int,
        income_sources: List[RetirementIncomeSource],
        loan_id: Optional[int] = None,
        loan_term_months: int = 360,
        down_payment: Decimal = ZERO,
        closing_costs: Decimal = ZERO,
        retirement_accounts: Optional[List[RetirementAccount]] = None,
        borrower_tax_bracket: Optional[Decimal] = None,
        filing_status: str = "single",
        other_income_annual: Decimal = ZERO,
        employment_income_monthly: Decimal = ZERO,
    ) -> RetirementIncomeResult:
        """
        Main entry point: validate and calculate qualifying retirement income.

        Args:
            org_id: Organization ID for tenant isolation.
            borrower_id: Borrower ID.
            income_sources: List of retirement income sources to validate.
            loan_id: Optional loan ID for persistence and DTI context.
            loan_term_months: Loan term for asset depletion (default 360 = 30yr).
            down_payment: Down payment amount for asset depletion netting.
            closing_costs: Closing costs for asset depletion netting.
            retirement_accounts: Accounts for asset depletion analysis.
            borrower_tax_bracket: Effective tax bracket for gross-up calculation.
            filing_status: "single", "married_filing_jointly", "married_filing_separately".
            other_income_annual: Other annual income (for SS taxability calculation).
            employment_income_monthly: Part-time or other employment income.

        Returns:
            RetirementIncomeResult with all validated sources and totals.
        """
        start_ms = int(time.time() * 1000)

        try:
            result = RetirementIncomeResult(
                org_id=org_id,
                borrower_id=borrower_id,
                loan_id=loan_id,
                has_employment_combo=employment_income_monthly > ZERO,
                employment_income_monthly=employment_income_monthly,
                calculated_at=datetime.now(timezone.utc),
            )

            if not income_sources and not retirement_accounts:
                result.success = False
                result.error = "No retirement income sources or accounts provided."
                result.flags.append(ValidationFlag(
                    code="NO_RETIREMENT_INCOME",
                    severity=FlagSeverity.WARNING,
                    message="No retirement income sources provided for validation.",
                ))
                return result

            # Step 1: validate and calculate each income source
            for source in income_sources:
                source_result = await self._validate_and_calculate_source(
                    org_id=org_id,
                    source=source,
                    borrower_tax_bracket=borrower_tax_bracket,
                    filing_status=filing_status,
                    other_income_annual=other_income_annual,
                )
                result.sources.append(source_result)

            # Step 2: asset depletion analysis (if accounts provided)
            if retirement_accounts:
                result.depletion_result = await self.analyze_asset_depletion(
                    accounts=retirement_accounts,
                    loan_term_months=loan_term_months,
                    down_payment=down_payment,
                    closing_costs=closing_costs,
                )
                # If depletion produces qualifying income, add as a source
                if result.depletion_result.monthly_income_from_depletion > ZERO:
                    depletion_source = RetirementIncomeSourceResult(
                        income_type=RetirementIncomeType.ASSET_DEPLETION,
                        payer_name="Asset Depletion Income",
                        raw_monthly=result.depletion_result.monthly_income_from_depletion,
                        qualifying_monthly=result.depletion_result.monthly_income_from_depletion,
                        qualifying_annual=result.depletion_result.annual_income_from_depletion,
                        is_eligible=result.depletion_result.is_sustainable,
                        confidence=65 if result.depletion_result.is_sustainable else 30,
                        flags=result.depletion_result.flags,
                        documentation_status="complete" if retirement_accounts else "missing",
                        notes=(
                            f"Asset depletion: {result.depletion_result.net_eligible_assets} "
                            f"net eligible over {loan_term_months} months"
                        ),
                    )
                    if not result.depletion_result.is_sustainable:
                        depletion_source.ineligible_reason = (
                            "Asset depletion income not sustainable for loan term"
                        )
                    result.sources.append(depletion_source)

            # Step 3: aggregate qualifying income (only eligible sources)
            eligible_sources = [s for s in result.sources if s.is_eligible]

            result.total_qualifying_monthly = sum(
                (s.qualifying_monthly for s in eligible_sources), ZERO
            ).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)

            result.total_qualifying_annual = (
                result.total_qualifying_monthly * MONTHS_PER_YEAR
            ).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)

            result.total_before_gross_up = sum(
                (s.raw_monthly for s in eligible_sources), ZERO
            ).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)

            result.total_gross_up_amount = sum(
                (
                    s.gross_up_result.gross_up_amount
                    if s.gross_up_applied and s.gross_up_result
                    else ZERO
                )
                for s in eligible_sources
            ).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)

            # Step 4: combined income if employment + retirement
            result.combined_monthly_income = (
                result.total_qualifying_monthly + employment_income_monthly
            ).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)

            # Step 5: confidence
            if eligible_sources:
                total_weight = sum(
                    float(s.qualifying_monthly) for s in eligible_sources
                    if s.qualifying_monthly > ZERO
                ) or 1.0
                weighted_conf = sum(
                    s.confidence * (float(s.qualifying_monthly) / total_weight)
                    for s in eligible_sources
                    if s.qualifying_monthly > ZERO
                )
                result.confidence = min(100, max(0, int(weighted_conf)))

            # Step 6: documentation requirements
            income_types = [s.income_type for s in income_sources]
            result.doc_requirements = await self.get_documentation_requirements(
                income_types
            )

            # Step 7: top-level flags and recommendations
            result.flags = self._generate_top_level_flags(result)
            result.recommendations = self._generate_recommendations(result)
            result.tasks_to_create = self._generate_tasks(result)

            # Step 8: persist
            if loan_id:
                duration_ms = int(time.time() * 1000) - start_ms
                await self._save_calculation(result, duration_ms)

            return result

        except Exception as e:
            logger.exception(
                "Retirement income calculation failed for org=%s borrower=%s: %s",
                org_id, borrower_id, e,
            )
            return RetirementIncomeResult(
                org_id=org_id,
                borrower_id=borrower_id,
                loan_id=loan_id,
                success=False,
                error=str(e),
            )

    # =========================================================================
    # 2. PER-SOURCE VALIDATION AND CALCULATION
    # =========================================================================

    async def _validate_and_calculate_source(
        self,
        org_id: str,
        source: RetirementIncomeSource,
        borrower_tax_bracket: Optional[Decimal],
        filing_status: str,
        other_income_annual: Decimal,
    ) -> RetirementIncomeSourceResult:
        """
        Validate a single retirement income source: continuance, docs,
        age restrictions, gross-up eligibility.
        """
        flags: List[ValidationFlag] = []
        monthly = source.monthly_amount
        annual = source.annual_amount or (monthly * MONTHS_PER_YEAR)

        # Ensure monthly/annual consistency
        if source.annual_amount and source.annual_amount > ZERO:
            derived_monthly = (source.annual_amount / MONTHS_PER_YEAR).quantize(
                TWO_PLACES, rounding=ROUND_HALF_UP
            )
            if monthly > ZERO and abs(monthly - derived_monthly) > Decimal("1.00"):
                flags.append(ValidationFlag(
                    code="MONTHLY_ANNUAL_MISMATCH",
                    severity=FlagSeverity.WARNING,
                    message=(
                        f"Monthly amount ${monthly} does not match annual/12 "
                        f"(${derived_monthly}). Using monthly as provided."
                    ),
                ))

        # --- Continuance validation ---
        continuance = await self.validate_continuance(
            income_type=source.income_type,
            documentation={
                "start_date": source.start_date,
                "expiration_date": source.expiration_date,
                "is_permanent": source.is_permanent,
                "plan_type": source.plan_type,
                "award_letter_on_file": source.award_letter_on_file,
                "benefit_statement_on_file": source.benefit_statement_on_file,
            },
        )
        flags.extend(continuance.flags)

        is_eligible = True
        ineligible_reason = None

        if continuance.status == ContinuanceStatus.EXPIRED:
            is_eligible = False
            ineligible_reason = "Income source has expired and cannot be used for qualification."
        elif continuance.status == ContinuanceStatus.EXPIRING:
            if (continuance.remaining_months or 0) < CONTINUANCE_MONTHS_REQUIRED:
                is_eligible = False
                ineligible_reason = (
                    f"Income expires in {continuance.remaining_months} months; "
                    f"minimum {CONTINUANCE_MONTHS_REQUIRED} months required."
                )

        # --- Age-based validation ---
        if source.borrower_date_of_birth:
            age_flags, age_eligible, age_reason = self._validate_age_requirements(
                income_type=source.income_type,
                dob=source.borrower_date_of_birth,
                monthly_amount=monthly,
            )
            flags.extend(age_flags)
            if not age_eligible:
                is_eligible = False
                ineligible_reason = age_reason

        # --- Documentation status ---
        doc_status = self._assess_documentation_status(source)
        if doc_status == "missing":
            flags.append(ValidationFlag(
                code="MISSING_DOCUMENTATION",
                severity=FlagSeverity.CRITICAL,
                message=f"Required documentation missing for {source.income_type.value}.",
            ))

        # --- Gross-up for non-taxable income ---
        gross_up_result = None
        qualifying_monthly = monthly

        if source.is_non_taxable and is_eligible:
            gross_up_result = await self.calculate_gross_up(
                non_taxable_amount=monthly,
                tax_bracket=borrower_tax_bracket,
                income_type=source.income_type,
                filing_status=filing_status,
                other_income_annual=other_income_annual,
                social_security_annual=annual if source.income_type == RetirementIncomeType.SOCIAL_SECURITY else ZERO,
            )
            qualifying_monthly = gross_up_result.grossed_up_monthly
            flags.extend(gross_up_result.flags)
        elif source.is_partially_taxable and is_eligible:
            # For partially taxable income (e.g., Social Security), gross up
            # only the non-taxable portion
            taxable_pct = source.taxable_percentage or Decimal("50.00")
            non_taxable_pct = Decimal("100.00") - taxable_pct
            non_taxable_monthly = (monthly * non_taxable_pct / Decimal("100")).quantize(
                TWO_PLACES, rounding=ROUND_HALF_UP
            )
            taxable_monthly = monthly - non_taxable_monthly

            gross_up_result = await self.calculate_gross_up(
                non_taxable_amount=non_taxable_monthly,
                tax_bracket=borrower_tax_bracket,
                income_type=source.income_type,
                filing_status=filing_status,
                other_income_annual=other_income_annual,
                social_security_annual=annual if source.income_type == RetirementIncomeType.SOCIAL_SECURITY else ZERO,
            )
            # Qualifying = taxable portion (as-is) + grossed-up non-taxable portion
            qualifying_monthly = (
                taxable_monthly + gross_up_result.grossed_up_monthly
            ).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
            flags.extend(gross_up_result.flags)

        qualifying_annual = (qualifying_monthly * MONTHS_PER_YEAR).quantize(
            TWO_PLACES, rounding=ROUND_HALF_UP
        )

        # --- COLA adjustment for Social Security (use current benefit, not historical) ---
        if source.income_type == RetirementIncomeType.SOCIAL_SECURITY:
            flags.append(ValidationFlag(
                code="SS_COLA_APPLIED",
                severity=FlagSeverity.INFO,
                message=(
                    "Social Security income should reflect current benefit amount "
                    "inclusive of COLA adjustments. Verify award letter shows "
                    "current benefit, not historical."
                ),
            ))

        # --- Confidence score ---
        confidence = self._calculate_source_confidence(
            source=source,
            continuance=continuance,
            doc_status=doc_status,
        )

        return RetirementIncomeSourceResult(
            income_type=source.income_type,
            payer_name=source.payer_name,
            raw_monthly=monthly,
            gross_up_applied=gross_up_result is not None and gross_up_result.gross_up_amount > ZERO,
            gross_up_result=gross_up_result,
            qualifying_monthly=qualifying_monthly if is_eligible else ZERO,
            qualifying_annual=qualifying_annual if is_eligible else ZERO,
            continuance=continuance,
            is_eligible=is_eligible,
            ineligible_reason=ineligible_reason,
            confidence=confidence,
            source_doc_ids=source.source_doc_ids,
            flags=flags,
            documentation_status=doc_status,
            notes=self._build_source_notes(source, continuance, gross_up_result),
        )

    # =========================================================================
    # 3. CONTINUANCE VALIDATION
    # =========================================================================

    async def validate_continuance(
        self,
        income_type: RetirementIncomeType,
        documentation: Dict[str, Any],
    ) -> ContinuanceResult:
        """
        Validate the 3-year continuance likelihood for a retirement income source.

        Per Fannie Mae B3-3.1-09, retirement income must be documented with a
        likelihood of continuing for at least 3 years from the mortgage date.

        Rules by type:
        - Social Security: generally permanent (no expiration)
        - VA Disability: permanent unless rated temporary
        - Pension (defined benefit): permanent if vested
        - Pension (defined contribution): depends on account balance
        - Disability (SSA): check review date
        - Disability (private): check policy expiration
        - IRA/401k distributions: depends on account sustainability
        """
        start_date = documentation.get("start_date")
        expiration_date = documentation.get("expiration_date")
        is_permanent = documentation.get("is_permanent", False)
        plan_type = documentation.get("plan_type")
        has_award_letter = documentation.get("award_letter_on_file", False)
        has_benefit_stmt = documentation.get("benefit_statement_on_file", False)

        flags: List[ValidationFlag] = []
        today = date.today()

        # --- Permanent income types ---
        if income_type in (
            RetirementIncomeType.SOCIAL_SECURITY,
            RetirementIncomeType.DISABILITY_SSA,
        ):
            # Social Security / SSDI are generally considered permanent
            documented = has_award_letter or has_benefit_stmt
            if not documented:
                flags.append(ValidationFlag(
                    code="MISSING_AWARD_LETTER",
                    severity=FlagSeverity.WARNING,
                    message=f"SSA award letter or benefit verification letter required for {income_type.value}.",
                ))

            # SSDI may have a review date
            if income_type == RetirementIncomeType.DISABILITY_SSA and expiration_date:
                remaining = self._months_remaining(expiration_date)
                if remaining is not None and remaining < CONTINUANCE_MONTHS_REQUIRED:
                    return ContinuanceResult(
                        income_type=income_type,
                        status=ContinuanceStatus.EXPIRING,
                        documented=documented,
                        remaining_months=remaining,
                        expiration_date=expiration_date,
                        flags=flags,
                        notes=f"SSDI review date {expiration_date} is within {CONTINUANCE_YEARS_REQUIRED} years.",
                    )

            return ContinuanceResult(
                income_type=income_type,
                status=ContinuanceStatus.PERMANENT,
                documented=documented,
                remaining_months=None,
                flags=flags,
                notes="Social Security / SSDI is considered permanent income.",
            )

        if income_type == RetirementIncomeType.VA_DISABILITY:
            documented = has_award_letter
            if not documented:
                flags.append(ValidationFlag(
                    code="MISSING_VA_AWARD",
                    severity=FlagSeverity.WARNING,
                    message="VA disability award letter required.",
                ))

            if is_permanent or expiration_date is None:
                return ContinuanceResult(
                    income_type=income_type,
                    status=ContinuanceStatus.PERMANENT,
                    documented=documented,
                    flags=flags,
                    notes="VA disability compensation is non-taxable and considered permanent.",
                )

            remaining = self._months_remaining(expiration_date)
            status = (
                ContinuanceStatus.LIKELY_TO_CONTINUE
                if remaining and remaining >= CONTINUANCE_MONTHS_REQUIRED
                else ContinuanceStatus.EXPIRING
            )
            return ContinuanceResult(
                income_type=income_type,
                status=status,
                documented=documented,
                remaining_months=remaining,
                expiration_date=expiration_date,
                flags=flags,
                notes=f"VA disability with expiration: {expiration_date}.",
            )

        if income_type == RetirementIncomeType.MILITARY_RETIREMENT:
            documented = has_award_letter or has_benefit_stmt
            if not documented:
                flags.append(ValidationFlag(
                    code="MISSING_RETIREMENT_DOCS",
                    severity=FlagSeverity.WARNING,
                    message="Military retirement award letter or DD Form 214 required.",
                ))
            return ContinuanceResult(
                income_type=income_type,
                status=ContinuanceStatus.PERMANENT,
                documented=documented,
                flags=flags,
                notes="Military retirement pay is considered permanent.",
            )

        if income_type in (RetirementIncomeType.PENSION, RetirementIncomeType.ANNUITY):
            documented = has_award_letter or has_benefit_stmt
            if not documented:
                flags.append(ValidationFlag(
                    code="MISSING_PENSION_DOCS",
                    severity=FlagSeverity.WARNING,
                    message="Pension/annuity award letter or benefit statement required.",
                ))

            if plan_type == "defined_benefit" or is_permanent:
                return ContinuanceResult(
                    income_type=income_type,
                    status=ContinuanceStatus.PERMANENT,
                    documented=documented,
                    flags=flags,
                    notes="Defined-benefit pension is considered permanent if vested.",
                )

            # Defined contribution or annuity with term
            if expiration_date:
                remaining = self._months_remaining(expiration_date)
                if remaining is not None and remaining < CONTINUANCE_MONTHS_REQUIRED:
                    flags.append(ValidationFlag(
                        code="PENSION_EXPIRING",
                        severity=FlagSeverity.CRITICAL,
                        message=(
                            f"Pension/annuity expires {expiration_date}, "
                            f"less than {CONTINUANCE_YEARS_REQUIRED} years from now."
                        ),
                    ))
                    return ContinuanceResult(
                        income_type=income_type,
                        status=ContinuanceStatus.EXPIRING,
                        documented=documented,
                        remaining_months=remaining,
                        expiration_date=expiration_date,
                        flags=flags,
                    )

            return ContinuanceResult(
                income_type=income_type,
                status=ContinuanceStatus.LIKELY_TO_CONTINUE,
                documented=documented,
                flags=flags,
                notes="Pension/annuity continuance verified; confirm plan terms.",
            )

        if income_type == RetirementIncomeType.DISABILITY_PRIVATE:
            documented = has_benefit_stmt
            if not documented:
                flags.append(ValidationFlag(
                    code="MISSING_DISABILITY_DOCS",
                    severity=FlagSeverity.WARNING,
                    message="Private disability policy benefit statement required.",
                ))

            if expiration_date:
                remaining = self._months_remaining(expiration_date)
                if remaining is not None and remaining < CONTINUANCE_MONTHS_REQUIRED:
                    flags.append(ValidationFlag(
                        code="DISABILITY_EXPIRING",
                        severity=FlagSeverity.CRITICAL,
                        message=(
                            f"Private disability benefits expire {expiration_date}, "
                            f"less than {CONTINUANCE_YEARS_REQUIRED} years."
                        ),
                    ))
                    return ContinuanceResult(
                        income_type=income_type,
                        status=ContinuanceStatus.EXPIRING,
                        documented=documented,
                        remaining_months=remaining,
                        expiration_date=expiration_date,
                        flags=flags,
                    )
                return ContinuanceResult(
                    income_type=income_type,
                    status=ContinuanceStatus.LIKELY_TO_CONTINUE,
                    documented=documented,
                    remaining_months=remaining,
                    expiration_date=expiration_date,
                    flags=flags,
                )

            if is_permanent:
                return ContinuanceResult(
                    income_type=income_type,
                    status=ContinuanceStatus.PERMANENT,
                    documented=documented,
                    flags=flags,
                )

            flags.append(ValidationFlag(
                code="UNKNOWN_DISABILITY_TERM",
                severity=FlagSeverity.WARNING,
                message="Private disability policy term not provided; cannot verify continuance.",
            ))
            return ContinuanceResult(
                income_type=income_type,
                status=ContinuanceStatus.UNKNOWN,
                documented=documented,
                flags=flags,
            )

        # IRA / 401k distributions -- continuance depends on account sustainability
        if income_type in (
            RetirementIncomeType.IRA_DISTRIBUTION,
            RetirementIncomeType.FOUR_OH_ONE_K,
        ):
            documented = has_benefit_stmt
            if not documented:
                flags.append(ValidationFlag(
                    code="MISSING_ACCOUNT_STATEMENTS",
                    severity=FlagSeverity.WARNING,
                    message="Retirement account statements required for distribution continuance.",
                ))

            # Cannot determine continuance without asset depletion analysis
            flags.append(ValidationFlag(
                code="DISTRIBUTION_SUSTAINABILITY",
                severity=FlagSeverity.INFO,
                message=(
                    "IRA/401k distribution continuance requires asset depletion analysis. "
                    "Provide account statements for sustainability verification."
                ),
            ))
            return ContinuanceResult(
                income_type=income_type,
                status=ContinuanceStatus.UNKNOWN,
                documented=documented,
                flags=flags,
                notes="Distribution continuance pending asset depletion analysis.",
            )

        # Fallback
        return ContinuanceResult(
            income_type=income_type,
            status=ContinuanceStatus.UNKNOWN,
            documented=False,
            flags=[ValidationFlag(
                code="UNKNOWN_INCOME_TYPE",
                severity=FlagSeverity.WARNING,
                message=f"Continuance rules not defined for {income_type.value}.",
            )],
        )

    # =========================================================================
    # 4. GROSS-UP CALCULATION
    # =========================================================================

    async def calculate_gross_up(
        self,
        non_taxable_amount: Decimal,
        tax_bracket: Optional[Decimal] = None,
        income_type: Optional[RetirementIncomeType] = None,
        filing_status: str = "single",
        other_income_annual: Decimal = ZERO,
        social_security_annual: Decimal = ZERO,
    ) -> GrossUpResult:
        """
        Calculate gross-up for non-taxable retirement income.

        Per Fannie Mae B3-3.1-01:
        - Non-taxable income may be grossed up by 25% (or the borrower's
          actual tax rate if documented, whichever is less)
        - VA disability compensation: 100% non-taxable, eligible for 25% gross-up
        - Social Security: partially taxable; gross up only the non-taxable portion

        The effective gross-up percentage is:
            min(25%, documented_tax_rate) if tax_bracket provided
            25% if no tax_bracket (default per Fannie Mae)

        For Social Security specifically:
        - Calculate the taxable portion based on combined income thresholds
        - Only gross up the non-taxable portion
        """
        flags: List[ValidationFlag] = []

        if non_taxable_amount <= ZERO:
            return GrossUpResult(
                original_monthly=non_taxable_amount,
                gross_up_percentage=ZERO,
                gross_up_amount=ZERO,
                grossed_up_monthly=non_taxable_amount,
                tax_exempt_type="none",
                calculation_detail="No non-taxable income to gross up.",
            )

        # Determine effective gross-up percentage
        if tax_bracket is not None and tax_bracket > ZERO:
            # Use the lesser of the documented tax rate or 25%
            effective_pct = min(tax_bracket, MAX_GROSS_UP_PCT)
            calc_detail = (
                f"Gross-up at {effective_pct}% (lesser of documented "
                f"tax bracket {tax_bracket}% and max {MAX_GROSS_UP_PCT}%)"
            )
        else:
            effective_pct = DEFAULT_GROSS_UP_PCT
            calc_detail = (
                f"Gross-up at default {DEFAULT_GROSS_UP_PCT}% per Fannie Mae B3-3.1-01 "
                f"(no documented tax bracket provided)"
            )

        # Determine tax-exempt classification
        if income_type == RetirementIncomeType.VA_DISABILITY:
            tax_exempt_type = "va_disability_100_nontaxable"
        elif income_type == RetirementIncomeType.SOCIAL_SECURITY:
            tax_exempt_type = "social_security_partial"
            # For Social Security, calculate the actual non-taxable portion
            # This method is called with only the non-taxable portion already
            # computed by the caller, so we just apply the gross-up
        elif income_type == RetirementIncomeType.DISABILITY_SSA:
            tax_exempt_type = "ssdi_nontaxable"
        elif income_type == RetirementIncomeType.MILITARY_RETIREMENT:
            tax_exempt_type = "military_partial"
        else:
            tax_exempt_type = "general_nontaxable"

        gross_up_amount = (
            non_taxable_amount * effective_pct / Decimal("100")
        ).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)

        grossed_up_monthly = (non_taxable_amount + gross_up_amount).quantize(
            TWO_PLACES, rounding=ROUND_HALF_UP
        )

        if effective_pct < DEFAULT_GROSS_UP_PCT and tax_bracket is not None:
            flags.append(ValidationFlag(
                code="REDUCED_GROSS_UP",
                severity=FlagSeverity.INFO,
                message=(
                    f"Gross-up reduced to {effective_pct}% based on borrower's "
                    f"documented tax bracket of {tax_bracket}%."
                ),
            ))

        return GrossUpResult(
            original_monthly=non_taxable_amount,
            gross_up_percentage=effective_pct,
            gross_up_amount=gross_up_amount,
            grossed_up_monthly=grossed_up_monthly,
            tax_exempt_type=tax_exempt_type,
            calculation_detail=calc_detail,
            flags=flags,
        )

    # =========================================================================
    # 5. SOCIAL SECURITY TAXABILITY CALCULATION
    # =========================================================================

    def calculate_ss_taxable_portion(
        self,
        ss_annual_benefit: Decimal,
        other_income_annual: Decimal,
        filing_status: str = "single",
    ) -> Tuple[Decimal, Decimal]:
        """
        Calculate the taxable and non-taxable portions of Social Security.

        IRS provisional income = AGI + non-taxable interest + 50% of SS benefits.

        Single filers:
        - Combined income < $25,000: 0% taxable
        - $25,000-$34,000: up to 50% taxable
        - > $34,000: up to 85% taxable

        Joint filers:
        - Combined income < $32,000: 0% taxable
        - $32,000-$44,000: up to 50% taxable
        - > $44,000: up to 85% taxable

        Returns:
            (taxable_percentage, non_taxable_percentage) as Decimal percentages.
        """
        if ss_annual_benefit <= ZERO:
            return (ZERO, Decimal("100.00"))

        half_ss = (ss_annual_benefit / 2).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
        combined_income = other_income_annual + half_ss

        if filing_status in ("married_filing_jointly", "married"):
            low_threshold = SS_JOINT_THRESHOLD_LOW
            high_threshold = SS_JOINT_THRESHOLD_HIGH
        else:
            low_threshold = SS_SINGLE_THRESHOLD_LOW
            high_threshold = SS_SINGLE_THRESHOLD_HIGH

        if combined_income < low_threshold:
            taxable_pct = ZERO
        elif combined_income < high_threshold:
            taxable_pct = Decimal("50.00")
        else:
            taxable_pct = SS_MAX_TAXABLE_PCT

        non_taxable_pct = (Decimal("100.00") - taxable_pct).quantize(
            TWO_PLACES, rounding=ROUND_HALF_UP
        )

        return (taxable_pct, non_taxable_pct)

    # =========================================================================
    # 6. ASSET DEPLETION ANALYSIS
    # =========================================================================

    async def analyze_asset_depletion(
        self,
        accounts: List[RetirementAccount],
        loan_term_months: int = 360,
        down_payment: Decimal = ZERO,
        closing_costs: Decimal = ZERO,
    ) -> DepletionResult:
        """
        Analyze asset depletion income per Fannie Mae B3-4.3-09.

        Formula:
            Eligible Assets = sum of:
                - Cash equivalents (checking, savings, CDs) at 100%
                - Market-risk assets (stocks, bonds, mutual funds, retirement) at 70%
            Net Eligible = Eligible Assets - Down Payment - Closing Costs
            Monthly Income = Net Eligible / Loan Term Months

        Conditions:
            - Only vested portions of retirement accounts count
            - Down payment and closing costs deducted from eligible assets
            - Borrower must be at least 62 (or receiving distributions) per
              some investor overlays; Fannie Mae does not impose age restriction
              on asset depletion itself
        """
        flags: List[ValidationFlag] = []
        account_results: List[DepletionAccountResult] = []
        total_eligible = ZERO

        for acct in accounts:
            raw_balance = acct.current_balance

            # Apply vesting percentage
            if acct.is_retirement_account and acct.vesting_percentage < Decimal("100.00"):
                vested_balance = (
                    raw_balance * acct.vesting_percentage / Decimal("100")
                ).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
                flags.append(ValidationFlag(
                    code="PARTIAL_VESTING",
                    severity=FlagSeverity.INFO,
                    message=(
                        f"Account {acct.institution_name or acct.account_type.value}: "
                        f"{acct.vesting_percentage}% vested "
                        f"(${raw_balance} -> ${vested_balance})."
                    ),
                ))
            else:
                vested_balance = raw_balance

            # Determine discount factor
            is_cash = acct.account_type in CASH_EQUIVALENT_TYPES
            if is_cash:
                discount_factor = CASH_EQUIVALENT_FACTOR
            elif acct.account_type in MARKET_RISK_TYPES:
                discount_factor = MARKET_RISK_DISCOUNT
            else:
                # Unknown account type -- apply market risk discount conservatively
                discount_factor = MARKET_RISK_DISCOUNT
                flags.append(ValidationFlag(
                    code="UNKNOWN_ACCOUNT_TYPE",
                    severity=FlagSeverity.WARNING,
                    message=(
                        f"Account type '{acct.account_type.value}' not explicitly categorized; "
                        f"applying {MARKET_RISK_DISCOUNT * 100}% market risk discount."
                    ),
                ))

            eligible_balance = (vested_balance * discount_factor).quantize(
                TWO_PLACES, rounding=ROUND_HALF_UP
            )

            account_results.append(DepletionAccountResult(
                account_type=acct.account_type,
                institution_name=acct.institution_name,
                raw_balance=raw_balance,
                discount_factor=discount_factor,
                eligible_balance=eligible_balance,
                is_cash_equivalent=is_cash,
                notes=f"{'100%' if is_cash else '70%'} credit applied.",
            ))

            total_eligible += eligible_balance

        # Net eligible after down payment and closing costs
        net_eligible = (total_eligible - down_payment - closing_costs).quantize(
            TWO_PLACES, rounding=ROUND_HALF_UP
        )

        if net_eligible < ZERO:
            flags.append(ValidationFlag(
                code="INSUFFICIENT_ASSETS",
                severity=FlagSeverity.CRITICAL,
                message=(
                    "Eligible assets do not cover down payment and closing costs. "
                    "No asset depletion income available."
                ),
            ))
            net_eligible = ZERO

        # Monthly income from depletion
        if loan_term_months > 0 and net_eligible > ZERO:
            monthly_income = (net_eligible / Decimal(loan_term_months)).quantize(
                TWO_PLACES, rounding=ROUND_HALF_UP
            )
        else:
            monthly_income = ZERO

        annual_income = (monthly_income * MONTHS_PER_YEAR).quantize(
            TWO_PLACES, rounding=ROUND_HALF_UP
        )

        # Sustainability check: is there enough for the full loan term?
        if monthly_income > ZERO:
            months_remaining = int(net_eligible / monthly_income) if monthly_income > ZERO else 0
        else:
            months_remaining = 0

        is_sustainable = months_remaining >= loan_term_months

        if not is_sustainable and monthly_income > ZERO:
            flags.append(ValidationFlag(
                code="DEPLETION_NOT_SUSTAINABLE",
                severity=FlagSeverity.WARNING,
                message=(
                    f"Asset depletion covers {months_remaining} months but "
                    f"loan term is {loan_term_months} months. "
                    f"Consider a shorter loan term or additional income sources."
                ),
            ))

        return DepletionResult(
            total_eligible_assets=total_eligible,
            down_payment=down_payment,
            closing_costs=closing_costs,
            net_eligible_assets=net_eligible,
            loan_term_months=loan_term_months,
            monthly_income_from_depletion=monthly_income,
            annual_income_from_depletion=annual_income,
            months_of_income_remaining=months_remaining,
            is_sustainable=is_sustainable,
            accounts=account_results,
            flags=flags,
            calculation_method="fannie_mae_b3_4_3_09",
        )

    # =========================================================================
    # 7. DOCUMENTATION REQUIREMENTS
    # =========================================================================

    async def get_documentation_requirements(
        self,
        income_types: List[RetirementIncomeType],
    ) -> List[DocRequirement]:
        """
        Return documentation requirements for each retirement income type.

        Requirements are based on Fannie Mae Selling Guide, FHA Handbook 4000.1,
        and VA Lender's Handbook Chapter 4.
        """
        requirements: List[DocRequirement] = []
        seen_types: set = set()

        for income_type in income_types:
            if income_type in seen_types:
                continue
            seen_types.add(income_type)

            if income_type == RetirementIncomeType.SOCIAL_SECURITY:
                requirements.extend([
                    DocRequirement(
                        doc_type="SSA_1099",
                        description="SSA-1099 (Social Security Benefit Statement)",
                        required=True,
                        years_needed=1,
                        notes="Most recent tax year. Confirms annual benefit amount.",
                    ),
                    DocRequirement(
                        doc_type="AWARD_LETTER",
                        description="Social Security Award Letter or Benefit Verification Letter",
                        required=True,
                        notes=(
                            "Must show current monthly benefit amount after COLA. "
                            "Can be obtained from ssa.gov or local SSA office."
                        ),
                    ),
                ])

            elif income_type == RetirementIncomeType.DISABILITY_SSA:
                requirements.extend([
                    DocRequirement(
                        doc_type="SSA_1099",
                        description="SSA-1099 showing disability benefit amount",
                        required=True,
                        years_needed=1,
                    ),
                    DocRequirement(
                        doc_type="DISABILITY_AWARD",
                        description="SSA Disability Award Letter",
                        required=True,
                        notes="Must include benefit amount and any review date.",
                    ),
                ])

            elif income_type == RetirementIncomeType.VA_DISABILITY:
                requirements.extend([
                    DocRequirement(
                        doc_type="VA_AWARD_LETTER",
                        description="VA Disability Compensation Award Letter",
                        required=True,
                        notes=(
                            "Must show disability rating percentage and monthly "
                            "compensation amount. VA disability is 100% non-taxable."
                        ),
                    ),
                ])

            elif income_type in (
                RetirementIncomeType.PENSION,
                RetirementIncomeType.ANNUITY,
            ):
                requirements.extend([
                    DocRequirement(
                        doc_type="1099_R",
                        description="Form 1099-R (Distributions from Pensions, Annuities, etc.)",
                        required=True,
                        years_needed=2,
                        notes="Most recent 2 years to establish distribution history.",
                    ),
                    DocRequirement(
                        doc_type="AWARD_LETTER",
                        description="Pension/Annuity Award Letter or Benefit Statement",
                        required=True,
                        notes=(
                            "For defined-benefit plans: verify benefit is permanent and vested. "
                            "For annuities: verify payout term covers at least 3 years."
                        ),
                    ),
                ])

            elif income_type in (
                RetirementIncomeType.IRA_DISTRIBUTION,
                RetirementIncomeType.FOUR_OH_ONE_K,
            ):
                requirements.extend([
                    DocRequirement(
                        doc_type="1099_R",
                        description="Form 1099-R showing distribution amounts",
                        required=True,
                        years_needed=2,
                        notes="Most recent 2 years of 1099-R forms.",
                    ),
                    DocRequirement(
                        doc_type="RETIREMENT_ACCOUNT_STATEMENT",
                        description="Current retirement account statement",
                        required=True,
                        notes=(
                            "Most recent 2 months of statements showing current "
                            "balance for asset depletion sustainability analysis."
                        ),
                    ),
                    DocRequirement(
                        doc_type="BENEFIT_STATEMENT",
                        description="Distribution schedule or automatic withdrawal confirmation",
                        required=False,
                        notes=(
                            "If regular distributions are set up, provide confirmation "
                            "of the automatic withdrawal schedule."
                        ),
                    ),
                ])

            elif income_type == RetirementIncomeType.MILITARY_RETIREMENT:
                requirements.extend([
                    DocRequirement(
                        doc_type="AWARD_LETTER",
                        description="Military Retirement Award Letter (DD Form 214 or RAS)",
                        required=True,
                        notes="Retiree Account Statement (RAS) from DFAS preferred.",
                    ),
                    DocRequirement(
                        doc_type="1099_R",
                        description="Form 1099-R for military retirement pay",
                        required=True,
                        years_needed=1,
                        notes="Confirms taxable vs. non-taxable portions.",
                    ),
                ])

            elif income_type == RetirementIncomeType.DISABILITY_PRIVATE:
                requirements.extend([
                    DocRequirement(
                        doc_type="BENEFIT_STATEMENT",
                        description="Private Disability Insurance Benefit Statement",
                        required=True,
                        notes="Must show monthly benefit amount and policy expiration date.",
                    ),
                    DocRequirement(
                        doc_type="1099_R",
                        description="Form 1099 or benefit payment history",
                        required=True,
                        years_needed=1,
                        notes="Verify consistency of payments received.",
                    ),
                ])

            elif income_type == RetirementIncomeType.ASSET_DEPLETION:
                requirements.extend([
                    DocRequirement(
                        doc_type="RETIREMENT_ACCOUNT_STATEMENT",
                        description="Current account statements for all eligible assets",
                        required=True,
                        notes=(
                            "Most recent 2 months of statements for each account. "
                            "Must show account type, balance, and vesting status."
                        ),
                    ),
                ])

        return requirements

    # =========================================================================
    # 8. AGE-BASED VALIDATION
    # =========================================================================

    def _validate_age_requirements(
        self,
        income_type: RetirementIncomeType,
        dob: date,
        monthly_amount: Decimal,
    ) -> Tuple[List[ValidationFlag], bool, Optional[str]]:
        """
        Validate age-related requirements for retirement income.

        Returns:
            (flags, is_eligible, ineligible_reason)
        """
        flags: List[ValidationFlag] = []
        today = date.today()
        age = self._calculate_age(dob)

        # Early withdrawal penalties for IRA/401k distributions under 59.5
        if income_type in (
            RetirementIncomeType.IRA_DISTRIBUTION,
            RetirementIncomeType.FOUR_OH_ONE_K,
        ):
            # 59.5 age check (use half-year precision)
            age_at_half = self._calculate_age_precise(dob)

            if age_at_half < Decimal("59.5"):
                penalty_amount = (
                    monthly_amount * EARLY_WITHDRAWAL_PENALTY_PCT / Decimal("100")
                ).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
                net_after_penalty = monthly_amount - penalty_amount

                flags.append(ValidationFlag(
                    code="EARLY_WITHDRAWAL_PENALTY",
                    severity=FlagSeverity.CRITICAL,
                    message=(
                        f"Borrower is {age} (under 59.5). Early withdrawal penalty "
                        f"of {EARLY_WITHDRAWAL_PENALTY_PCT}% applies: "
                        f"${monthly_amount}/mo reduces to ${net_after_penalty}/mo "
                        f"after penalty. Verify if exceptions apply "
                        f"(72(t) SEPP, disability, etc.)."
                    ),
                ))

                # Adjust the effective amount for qualification
                # Note: the penalty affects net income but the distribution
                # itself is still the stated amount for gross income purposes.
                # Flag for LO review.

            # RMD compliance check
            if age >= RMD_AGE and monthly_amount <= ZERO:
                flags.append(ValidationFlag(
                    code="RMD_NOT_TAKEN",
                    severity=FlagSeverity.WARNING,
                    message=(
                        f"Borrower is {age} (at or above RMD age of {RMD_AGE}). "
                        f"Required Minimum Distributions should be taken. "
                        f"Verify RMD compliance with account custodian."
                    ),
                ))

        # Social Security age validation
        if income_type == RetirementIncomeType.SOCIAL_SECURITY:
            if age < SOCIAL_SECURITY_EARLY_AGE:
                flags.append(ValidationFlag(
                    code="SS_UNDER_MINIMUM_AGE",
                    severity=FlagSeverity.CRITICAL,
                    message=(
                        f"Borrower is {age}, under minimum Social Security "
                        f"retirement age of {SOCIAL_SECURITY_EARLY_AGE}. "
                        f"Verify this is SSDI or survivor benefits."
                    ),
                ))
            elif age < SOCIAL_SECURITY_FULL_AGE:
                flags.append(ValidationFlag(
                    code="SS_EARLY_RETIREMENT",
                    severity=FlagSeverity.INFO,
                    message=(
                        f"Borrower is {age}, claiming Social Security before "
                        f"full retirement age ({SOCIAL_SECURITY_FULL_AGE}). "
                        f"Benefits are permanently reduced but current amount "
                        f"is acceptable for qualification."
                    ),
                ))

        # Under-62 receiving retirement distributions gets extra scrutiny
        if age < 62 and income_type in (
            RetirementIncomeType.PENSION,
            RetirementIncomeType.ANNUITY,
            RetirementIncomeType.IRA_DISTRIBUTION,
            RetirementIncomeType.FOUR_OH_ONE_K,
        ):
            flags.append(ValidationFlag(
                code="UNDER_62_RETIREMENT",
                severity=FlagSeverity.WARNING,
                message=(
                    f"Borrower is {age} and receiving retirement distributions. "
                    f"Additional scrutiny required: verify early retirement "
                    f"eligibility, penalty exemptions, and distribution sustainability."
                ),
            ))

        return (flags, True, None)

    # =========================================================================
    # 9. DOCUMENTATION STATUS ASSESSMENT
    # =========================================================================

    def _assess_documentation_status(
        self,
        source: RetirementIncomeSource,
    ) -> str:
        """
        Assess documentation completeness for a retirement income source.

        Returns: "complete", "incomplete", or "missing"
        """
        if source.income_type == RetirementIncomeType.SOCIAL_SECURITY:
            if source.ssa_1099_on_file and source.award_letter_on_file:
                return "complete"
            if source.ssa_1099_on_file or source.award_letter_on_file:
                return "incomplete"
            return "missing"

        if source.income_type == RetirementIncomeType.VA_DISABILITY:
            return "complete" if source.award_letter_on_file else "missing"

        if source.income_type == RetirementIncomeType.DISABILITY_SSA:
            if source.ssa_1099_on_file and source.award_letter_on_file:
                return "complete"
            if source.ssa_1099_on_file or source.award_letter_on_file:
                return "incomplete"
            return "missing"

        if source.income_type in (
            RetirementIncomeType.PENSION,
            RetirementIncomeType.ANNUITY,
        ):
            if source.form_1099r_on_file and source.award_letter_on_file:
                return "complete"
            if source.form_1099r_on_file or source.award_letter_on_file:
                return "incomplete"
            return "missing"

        if source.income_type in (
            RetirementIncomeType.IRA_DISTRIBUTION,
            RetirementIncomeType.FOUR_OH_ONE_K,
        ):
            if source.form_1099r_on_file and source.account_statements_on_file:
                return "complete"
            if source.form_1099r_on_file or source.account_statements_on_file:
                return "incomplete"
            return "missing"

        if source.income_type == RetirementIncomeType.MILITARY_RETIREMENT:
            if source.award_letter_on_file and source.form_1099r_on_file:
                return "complete"
            if source.award_letter_on_file or source.form_1099r_on_file:
                return "incomplete"
            return "missing"

        if source.income_type == RetirementIncomeType.DISABILITY_PRIVATE:
            if source.benefit_statement_on_file:
                return "complete"
            return "missing"

        return "incomplete"

    # =========================================================================
    # 10. CONFIDENCE SCORING
    # =========================================================================

    def _calculate_source_confidence(
        self,
        source: RetirementIncomeSource,
        continuance: ContinuanceResult,
        doc_status: str,
    ) -> int:
        """
        Calculate confidence score (0-100) for a retirement income source.
        """
        confidence = 50  # baseline

        # Documentation completeness
        if doc_status == "complete":
            confidence += 25
        elif doc_status == "incomplete":
            confidence += 10
        # "missing" gets no bonus

        # Continuance status
        if continuance.status == ContinuanceStatus.PERMANENT:
            confidence += 20
        elif continuance.status == ContinuanceStatus.LIKELY_TO_CONTINUE:
            confidence += 15
        elif continuance.status == ContinuanceStatus.EXPIRING:
            confidence -= 10
        elif continuance.status == ContinuanceStatus.UNKNOWN:
            confidence -= 5

        # Income type reliability
        if source.income_type in (
            RetirementIncomeType.SOCIAL_SECURITY,
            RetirementIncomeType.VA_DISABILITY,
            RetirementIncomeType.MILITARY_RETIREMENT,
        ):
            confidence += 5  # Government-backed, highly reliable

        # Penalize for missing DOB (can't do age validation)
        if source.borrower_date_of_birth is None:
            confidence -= 5

        return min(100, max(0, confidence))

    # =========================================================================
    # 11. FLAG GENERATION (TOP-LEVEL)
    # =========================================================================

    def _generate_top_level_flags(
        self,
        result: RetirementIncomeResult,
    ) -> List[ValidationFlag]:
        """Generate top-level flags from all source-level flags and overall analysis."""
        flags: List[ValidationFlag] = []

        # Collect all source-level flags
        for source in result.sources:
            flags.extend(source.flags)

        # Depletion flags
        if result.depletion_result:
            flags.extend(result.depletion_result.flags)

        # Employment + retirement combo check
        if result.has_employment_combo:
            total_retirement = result.total_qualifying_monthly
            employment = result.employment_income_monthly
            combined = total_retirement + employment

            if combined > ZERO:
                retirement_pct = (total_retirement / combined * Decimal("100")).quantize(
                    TWO_PLACES, rounding=ROUND_HALF_UP
                )
                flags.append(ValidationFlag(
                    code="EMPLOYMENT_RETIREMENT_COMBO",
                    severity=FlagSeverity.INFO,
                    message=(
                        f"Combined income: ${combined}/mo "
                        f"(retirement {retirement_pct}%, employment "
                        f"{(Decimal('100') - retirement_pct).quantize(TWO_PLACES)}%). "
                        f"Verify sustainability of both income streams."
                    ),
                ))

        # Multiple retirement sources
        eligible_count = len([s for s in result.sources if s.is_eligible])
        if eligible_count > 3:
            flags.append(ValidationFlag(
                code="MULTIPLE_RETIREMENT_SOURCES",
                severity=FlagSeverity.INFO,
                message=(
                    f"Borrower has {eligible_count} qualifying retirement income sources. "
                    f"Verify each is properly documented."
                ),
            ))

        # Ineligible sources
        ineligible = [s for s in result.sources if not s.is_eligible]
        for s in ineligible:
            flags.append(ValidationFlag(
                code="INELIGIBLE_SOURCE",
                severity=FlagSeverity.WARNING,
                message=(
                    f"{s.income_type.value}: Not eligible for qualification. "
                    f"Reason: {s.ineligible_reason or 'Unknown'}"
                ),
            ))

        # De-duplicate by code + message
        seen = set()
        unique_flags = []
        for f in flags:
            key = f"{f.code}:{f.message}"
            if key not in seen:
                seen.add(key)
                unique_flags.append(f)

        return unique_flags

    # =========================================================================
    # 12. RECOMMENDATION GENERATION
    # =========================================================================

    def _generate_recommendations(
        self,
        result: RetirementIncomeResult,
    ) -> List[str]:
        """Generate actionable recommendations for the LO."""
        recs: List[str] = []

        flag_codes = {f.code for f in result.flags}

        if "NO_RETIREMENT_INCOME" in flag_codes:
            recs.append(
                "No retirement income sources provided. If borrower receives "
                "Social Security, pension, or other retirement income, obtain "
                "award letters and most recent 1099-R/SSA-1099 forms."
            )

        if "MISSING_AWARD_LETTER" in flag_codes:
            recs.append(
                "Obtain SSA award letter or benefit verification letter from "
                "ssa.gov. This must show the current monthly benefit amount "
                "inclusive of COLA adjustments."
            )

        if "MISSING_VA_AWARD" in flag_codes:
            recs.append(
                "Obtain VA disability compensation award letter showing "
                "disability rating and monthly compensation amount. "
                "VA disability income is 100% non-taxable and eligible "
                "for 25% gross-up."
            )

        if "MISSING_PENSION_DOCS" in flag_codes:
            recs.append(
                "Obtain pension/annuity award letter or benefit statement "
                "confirming monthly benefit amount, plan type (defined benefit "
                "vs. defined contribution), and vesting status."
            )

        if "MISSING_ACCOUNT_STATEMENTS" in flag_codes:
            recs.append(
                "Obtain most recent 2 months of retirement account statements "
                "showing current balance. Required for asset depletion analysis "
                "to verify distribution sustainability."
            )

        if "EARLY_WITHDRAWAL_PENALTY" in flag_codes:
            recs.append(
                "Borrower is under 59.5 and taking retirement distributions. "
                "Verify if a 72(t) Substantially Equal Periodic Payment (SEPP) "
                "plan or other penalty exception applies. If penalty applies, "
                "net income after 10% penalty should be used."
            )

        if "PENSION_EXPIRING" in flag_codes or "DISABILITY_EXPIRING" in flag_codes:
            recs.append(
                "Income source expires within 3 years. Per Fannie Mae guidelines, "
                "income must have a reasonable expectation of continuing for at "
                "least 3 years. This income cannot be used for qualification "
                "unless the borrower can provide evidence of renewal or extension."
            )

        if "DEPLETION_NOT_SUSTAINABLE" in flag_codes:
            recs.append(
                "Asset depletion income is not sustainable for the full loan term. "
                "Consider a shorter loan term, additional income sources, or "
                "a smaller loan amount."
            )

        if "INSUFFICIENT_ASSETS" in flag_codes:
            recs.append(
                "Eligible assets after discount do not cover down payment and "
                "closing costs. Asset depletion income cannot be used. "
                "Verify all accounts are included and balances are current."
            )

        if "SS_UNDER_MINIMUM_AGE" in flag_codes:
            recs.append(
                "Borrower is under 62 and claiming Social Security. Verify "
                "this is SSDI (disability) or survivor benefits, not "
                "early retirement. Obtain appropriate award documentation."
            )

        if "UNDER_62_RETIREMENT" in flag_codes:
            recs.append(
                "Borrower under 62 receiving retirement distributions requires "
                "additional scrutiny. Document the reason for early distributions "
                "and verify no early withdrawal penalties apply, or account for "
                "the 10% penalty in qualifying income."
            )

        if "RMD_NOT_TAKEN" in flag_codes:
            recs.append(
                "Borrower is at or above RMD age but no distributions reported. "
                "Verify RMD compliance with the account custodian. "
                "Failure to take RMDs incurs IRS penalties."
            )

        if "MISSING_DOCUMENTATION" in flag_codes:
            recs.append(
                "Critical documentation is missing for one or more retirement "
                "income sources. Income cannot be used for qualification until "
                "required documents are obtained."
            )

        if result.has_employment_combo:
            recs.append(
                "Borrower has both employment and retirement income. Verify "
                "employment is part-time or consistent with retirement status. "
                "Both income streams can be used if properly documented."
            )

        # De-duplicate
        seen = set()
        unique_recs = []
        for r in recs:
            key = r[:80]
            if key not in seen:
                seen.add(key)
                unique_recs.append(r)

        return unique_recs

    # =========================================================================
    # 13. TASK GENERATION
    # =========================================================================

    def _generate_tasks(
        self,
        result: RetirementIncomeResult,
    ) -> List[Dict]:
        """Create task definitions for LO follow-up items."""
        tasks: List[Dict] = []
        flag_codes = {f.code for f in result.flags}

        if "MISSING_AWARD_LETTER" in flag_codes:
            tasks.append({
                "task_type": "request_documentation",
                "title": "Obtain SSA Award Letter / Benefit Verification",
                "description": "Social Security award letter or benefit verification letter required.",
                "priority": "high",
                "ai_recommendation": (
                    "Request current SSA benefit verification letter from borrower. "
                    "Can be obtained online at ssa.gov/myaccount or from local SSA office."
                ),
            })

        if "MISSING_VA_AWARD" in flag_codes:
            tasks.append({
                "task_type": "request_documentation",
                "title": "Obtain VA Disability Award Letter",
                "description": "VA disability compensation award letter required.",
                "priority": "high",
                "ai_recommendation": (
                    "Request VA disability award letter showing rating percentage "
                    "and monthly compensation. Available from VA eBenefits portal."
                ),
            })

        if "MISSING_PENSION_DOCS" in flag_codes:
            tasks.append({
                "task_type": "request_documentation",
                "title": "Obtain Pension/Annuity Documentation",
                "description": "Pension or annuity award letter and benefit statement required.",
                "priority": "high",
                "ai_recommendation": (
                    "Contact pension plan administrator for benefit verification letter "
                    "showing monthly amount, plan type, and vesting status."
                ),
            })

        if "MISSING_ACCOUNT_STATEMENTS" in flag_codes:
            tasks.append({
                "task_type": "request_documentation",
                "title": "Obtain Retirement Account Statements",
                "description": "Current retirement account statements required for asset depletion.",
                "priority": "high",
                "ai_recommendation": (
                    "Request most recent 2 months of statements for all retirement "
                    "accounts (IRA, 401k, brokerage). Must show current balance."
                ),
            })

        if "MISSING_RETIREMENT_DOCS" in flag_codes:
            tasks.append({
                "task_type": "request_documentation",
                "title": "Obtain Military Retirement Documentation",
                "description": "Military retirement award letter or RAS from DFAS required.",
                "priority": "high",
                "ai_recommendation": (
                    "Request Retiree Account Statement (RAS) from DFAS or DD Form 214 "
                    "with retirement pay documentation."
                ),
            })

        if "MISSING_DISABILITY_DOCS" in flag_codes:
            tasks.append({
                "task_type": "request_documentation",
                "title": "Obtain Private Disability Documentation",
                "description": "Private disability insurance benefit statement required.",
                "priority": "high",
                "ai_recommendation": (
                    "Request disability insurance benefit statement showing monthly "
                    "amount, policy expiration date, and any review provisions."
                ),
            })

        if "EARLY_WITHDRAWAL_PENALTY" in flag_codes:
            tasks.append({
                "task_type": "review_income",
                "title": "Review Early Withdrawal Penalty Impact",
                "description": "Borrower under 59.5 taking retirement distributions.",
                "priority": "critical",
                "ai_recommendation": (
                    "Verify if 72(t) SEPP plan or other penalty exception applies. "
                    "If no exception, reduce qualifying income by 10% penalty amount. "
                    "Document penalty exception with IRS Form 5329 if applicable."
                ),
            })

        if "PENSION_EXPIRING" in flag_codes or "DISABILITY_EXPIRING" in flag_codes:
            tasks.append({
                "task_type": "review_continuance",
                "title": "Review Expiring Income Source",
                "description": "Retirement/disability income expires within 3 years.",
                "priority": "critical",
                "ai_recommendation": (
                    "Income source does not meet 3-year continuance requirement. "
                    "Obtain evidence of benefit renewal or extension, or exclude "
                    "from qualifying income."
                ),
            })

        if "DEPLETION_NOT_SUSTAINABLE" in flag_codes or "INSUFFICIENT_ASSETS" in flag_codes:
            tasks.append({
                "task_type": "review_income",
                "title": "Review Asset Depletion Sustainability",
                "description": "Asset depletion income may not be sustainable for loan term.",
                "priority": "high",
                "ai_recommendation": (
                    "Review asset depletion analysis. Consider shorter loan term, "
                    "additional income sources, or smaller loan amount."
                ),
            })

        if "SS_UNDER_MINIMUM_AGE" in flag_codes:
            tasks.append({
                "task_type": "verify_income",
                "title": "Verify Social Security Benefit Type",
                "description": "Borrower under 62 claiming Social Security benefits.",
                "priority": "critical",
                "ai_recommendation": (
                    "Verify this is SSDI or survivor benefits. "
                    "Obtain appropriate award letter specifying benefit type."
                ),
            })

        if "RMD_NOT_TAKEN" in flag_codes:
            tasks.append({
                "task_type": "verify_compliance",
                "title": "Verify RMD Compliance",
                "description": "Borrower at RMD age with no reported distributions.",
                "priority": "medium",
                "ai_recommendation": (
                    "Confirm with account custodian that RMDs are being taken. "
                    "Failure to take RMDs results in IRS penalties that may "
                    "affect qualification."
                ),
            })

        if "MISSING_DOCUMENTATION" in flag_codes:
            tasks.append({
                "task_type": "request_documentation",
                "title": "Obtain Missing Retirement Income Documentation",
                "description": "Critical documentation missing for retirement income qualification.",
                "priority": "critical",
                "ai_recommendation": (
                    "Review documentation requirements list and request all "
                    "missing documents from borrower. Income cannot be used "
                    "for qualification until docs are received."
                ),
            })

        return tasks

    # =========================================================================
    # 14. PERSISTENCE
    # =========================================================================

    async def _save_calculation(
        self,
        result: RetirementIncomeResult,
        duration_ms: int = 0,
    ) -> Optional[int]:
        """
        Persist retirement income calculation to income_calculations and
        income_sources tables. Returns the calculation_id.
        """
        try:
            # Serialize flags for JSON storage
            flags_json = json.dumps([
                {
                    "code": f.code,
                    "severity": f.severity.value,
                    "message": f.message,
                    "field": f.field,
                }
                for f in result.flags
            ])

            recs_json = json.dumps(result.recommendations)
            now = datetime.now(timezone.utc)

            all_doc_ids = list({
                did
                for s in result.sources
                for did in s.source_doc_ids
            })

            calc_row = self.db.execute(
                text("""
                    INSERT INTO income_calculations (
                        loan_id, borrower_id,
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
                        :loan_id, :borrower_id,
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
                    "loan_id": result.loan_id,
                    "borrower_id": result.borrower_id,
                    "calc_type": "retirement",
                    "status": "needs_review" if result.flags else "completed",
                    "total_monthly": float(result.total_qualifying_monthly),
                    "total_annual": float(result.total_qualifying_annual),
                    "method": "retirement_income_validation",
                    "confidence": result.confidence,
                    "flags": flags_json,
                    "recommendations": recs_json,
                    "duration": duration_ms,
                    "source_docs": json.dumps(all_doc_ids),
                    "now": now,
                },
            )
            calculation_id = calc_row.fetchone()[0]

            # Save each source
            for idx, source in enumerate(result.sources):
                source_flags_json = json.dumps([
                    {"code": f.code, "severity": f.severity.value, "message": f.message}
                    for f in source.flags
                ])

                gross_up_detail = ""
                if source.gross_up_result:
                    gross_up_detail = (
                        f"Gross-up: {source.gross_up_result.gross_up_percentage}% "
                        f"(${source.gross_up_result.gross_up_amount}/mo)"
                    )

                notes = source.notes
                if gross_up_detail:
                    notes = f"{notes} | {gross_up_detail}" if notes else gross_up_detail

                self.db.execute(
                    text("""
                        INSERT INTO income_sources (
                            calculation_id, borrower_id,
                            source_type, employer_name, position_title,
                            is_primary,
                            base_monthly_income,
                            overtime_monthly, bonus_monthly,
                            commission_monthly, other_monthly,
                            total_monthly_income, total_annual_income,
                            trending_direction,
                            verification_status,
                            source_document_ids,
                            ai_confidence, ai_notes,
                            created_at, updated_at
                        ) VALUES (
                            :calc_id, :borrower_id,
                            :source_type, :payer, NULL,
                            :is_primary,
                            :base_monthly,
                            0, 0, 0, 0,
                            :total_monthly, :total_annual,
                            :trending,
                            :verification_status,
                            :doc_ids,
                            :confidence, :notes,
                            :now, :now
                        )
                    """),
                    {
                        "calc_id": calculation_id,
                        "borrower_id": result.borrower_id,
                        "source_type": source.income_type.value,
                        "payer": source.payer_name,
                        "is_primary": idx == 0,
                        "base_monthly": float(source.qualifying_monthly),
                        "total_monthly": float(source.qualifying_monthly),
                        "total_annual": float(source.qualifying_annual),
                        "trending": "stable",
                        "verification_status": source.documentation_status,
                        "doc_ids": json.dumps(source.source_doc_ids),
                        "confidence": source.confidence,
                        "notes": notes,
                        "now": now,
                    },
                )

            # Save tasks
            for task in result.tasks_to_create:
                self.db.execute(
                    text("""
                        INSERT INTO income_verification_tasks (
                            calculation_id,
                            loan_id, organization_id,
                            task_type, title, description,
                            priority, status,
                            ai_recommendation,
                            created_at, updated_at
                        ) VALUES (
                            :calc_id,
                            :loan_id, :org_id,
                            :task_type, :title, :description,
                            :priority, 'open',
                            :ai_rec,
                            :now, :now
                        )
                    """),
                    {
                        "calc_id": calculation_id,
                        "loan_id": result.loan_id,
                        "org_id": result.org_id,
                        "task_type": task["task_type"],
                        "title": task["title"],
                        "description": task["description"],
                        "priority": task["priority"],
                        "ai_rec": task.get("ai_recommendation", ""),
                        "now": now,
                    },
                )

            self.db.commit()

            logger.info(
                "Retirement income calculation saved: id=%d org=%s borrower=%d "
                "monthly=$%s sources=%d tasks=%d",
                calculation_id, result.org_id, result.borrower_id,
                result.total_qualifying_monthly, len(result.sources),
                len(result.tasks_to_create),
            )

            return calculation_id

        except Exception as e:
            self.db.rollback()
            logger.exception("Failed to save retirement income calculation: %s", e)
            return None

    # =========================================================================
    # 15. HELPER METHODS
    # =========================================================================

    def _calculate_age(self, dob: date) -> int:
        """Calculate age in whole years from date of birth."""
        today = date.today()
        age = today.year - dob.year
        if (today.month, today.day) < (dob.month, dob.day):
            age -= 1
        return age

    def _calculate_age_precise(self, dob: date) -> Decimal:
        """Calculate age with half-year precision (for 59.5 check)."""
        today = date.today()
        delta = today - dob
        return (Decimal(str(delta.days)) / Decimal("365.25")).quantize(
            Decimal("0.1"), rounding=ROUND_HALF_UP
        )

    def _months_remaining(self, expiration_date: date) -> Optional[int]:
        """Calculate months remaining until expiration."""
        today = date.today()
        if expiration_date <= today:
            return 0
        delta = expiration_date - today
        return max(0, int(delta.days / 30.44))

    def _build_source_notes(
        self,
        source: RetirementIncomeSource,
        continuance: ContinuanceResult,
        gross_up_result: Optional[GrossUpResult],
    ) -> str:
        """Build human-readable notes for a source."""
        parts = []

        parts.append(f"{source.income_type.value}: ${source.monthly_amount}/mo")

        if continuance.status == ContinuanceStatus.PERMANENT:
            parts.append("Continuance: permanent")
        elif continuance.status == ContinuanceStatus.LIKELY_TO_CONTINUE:
            parts.append("Continuance: likely to continue 3+ years")
        elif continuance.status == ContinuanceStatus.EXPIRING:
            parts.append(f"Continuance: expiring ({continuance.remaining_months} months)")
        elif continuance.status == ContinuanceStatus.UNKNOWN:
            parts.append("Continuance: unknown -- needs verification")

        if gross_up_result and gross_up_result.gross_up_amount > ZERO:
            parts.append(
                f"Gross-up: {gross_up_result.gross_up_percentage}% "
                f"(+${gross_up_result.gross_up_amount}/mo)"
            )

        if source.is_non_taxable:
            parts.append("Tax status: non-taxable")
        elif source.is_partially_taxable:
            parts.append(
                f"Tax status: partially taxable "
                f"({source.taxable_percentage or 'unknown'}% taxable)"
            )

        return " | ".join(parts)


# =============================================================================
# FACTORY FUNCTION
# =============================================================================

def get_retirement_income_service(db: Session) -> RetirementIncomeService:
    """
    Factory function returning a RetirementIncomeService for the given session.

    Usage:
        service = get_retirement_income_service(db)
        result = await service.calculate_retirement_income(...)
    """
    return RetirementIncomeService(db)
