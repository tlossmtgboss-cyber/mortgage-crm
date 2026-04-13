"""
Investor Rules Engine for Income Calculations
===============================================

Centralizes all income calculation rules (gross-up factors, history requirements,
vacancy factors, trending thresholds, confidence routing) that are currently
hardcoded across the three calculation engines:

    - income_calculation_service.py (legacy)
    - unified_income_calculator.py (current)
    - ai_income_detection_service.py (AI detection)

Rules are organized by investor/program type with sensible FNMA defaults.
Pre-built rule sets cover FNMA, FHA, VA, USDA, and Non-QM programs.

Future: Rules will be stored per-investor in an ``investor_rule_configs`` database
table, allowing loan officers and admins to customize rules without code changes.

References:
    - FNMA Selling Guide B3-3.1-01 (03/04/2026): Employment income documentation
    - FNMA Selling Guide B3-3.1-09: Rental income
    - FNMA Selling Guide B3-3.1-24: Non-taxable income gross-up
    - HUD 4000.1 II.A.4: FHA income requirements
    - VA Pamphlet 26-7 Ch. 9: VA income analysis
    - USDA HB-1-3550 Ch. 9: USDA income requirements
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Rule dataclasses
# ---------------------------------------------------------------------------

@dataclass
class IncomeHistoryRules:
    """Documentation and history requirements by income type.

    These control the minimum documentation periods underwriters require
    before qualifying various income sources.

    References:
        - FNMA B3-3.1-01 (03/04/2026): Base employment reduced to 1 year for
          W-2 borrowers with strong compensating factors.
        - FNMA B3-3.1-02: Variable income (OT, bonus) requires 12-24 months
          history depending on stability.
        - FNMA B3-3.1-09: Rental income requires 2 years Schedule E.
        - HUD 4000.1 II.A.4.b: FHA requires 2 years landlord experience for
          rental income to offset PITIA.
        - FNMA B3-3.1-06: Self-employment requires 2 years tax returns unless
          5+ years in same business with increasing income.
    """

    # W-2 employment
    base_employment_w2_years: int = 1
    """Minimum years of W-2 employment history. Updated per FNMA B3-3.1-01
    (03/04/2026) -- reduced from 2 to 1 year for standard W-2 borrowers."""

    base_employment_paystub_days: int = 30
    """Maximum age (in days) of the most recent paystub. FNMA requires paystub
    covering at least 30 days of employment with YTD earnings."""

    # Variable income (overtime, bonus, commission)
    variable_income_history_months: int = 24
    """Months of history required for overtime, bonus, and commission income.
    FNMA B3-3.1-02 requires 12-24 months; 24 is the conservative standard."""

    # Self-employment
    self_employment_tax_return_years: int = 2
    """Years of tax returns required for self-employed borrowers. FNMA B3-3.1-06
    requires 2 years. May be reduced to 1 year for Non-QM programs."""

    # Rental income
    rental_schedule_e_years: int = 2
    """Years of Schedule E required for existing rental properties. FNMA B3-3.1-09."""

    rental_landlord_experience_years: int = 0
    """Years of landlord experience required. FNMA does not require prior
    experience (0); FHA requires 2 years per HUD 4000.1 II.A.4.b.(3)."""

    # Other income sources
    alimony_receipt_months: int = 6
    """Months of documented alimony/child support receipt history."""

    alimony_continuation_years: int = 3
    """Years that alimony/child support must continue for qualification.
    FNMA B3-3.1-09 requires at least 3 years remaining."""


@dataclass
class GrossUpRules:
    """Non-taxable income gross-up factors by program type.

    When a borrower receives non-taxable income (VA disability, Social Security,
    child support, etc.), underwriters gross it up by multiplying by a factor to
    make it comparable to taxable income for DTI purposes.

    References:
        - FNMA B3-3.1-24: "If the income is verified to be nontaxable, and
          the income and its tax-exempt status are likely to continue, the
          lender may develop an adjusted gross income for the borrower by
          adding an amount equivalent to 25% of the nontaxable income."
        - HUD 4000.1 II.A.4.d.(4): FHA allows 25% gross-up for nontaxable
          income with documentation of nontaxable status.
        - VA Pamphlet 26-7 Ch. 9.17: VA allows 25% gross-up.
        - USDA HB-1-3550: USDA generally does NOT gross up nontaxable income
          for household income limit calculations (program-specific).
    """

    conventional: float = 1.25
    """Gross-up factor for conventional (FNMA/FHLMC) loans. 25% = 1.25x."""

    fha: float = 1.25
    """Gross-up factor for FHA loans. 25% per HUD 4000.1."""

    va: float = 1.25
    """Gross-up factor for VA loans. 25% per VA Pamphlet 26-7."""

    usda: float = 1.0
    """Gross-up factor for USDA loans. No gross-up (1.0x) -- USDA uses actual
    income for household income limits. Some lenders allow gross-up for
    repayment income; default to conservative no-gross-up."""

    def for_program(self, program_type: str) -> float:
        """Return the gross-up factor for a given program type.

        Args:
            program_type: One of CONVENTIONAL, FHA, VA, USDA, NON_QM.

        Returns:
            The gross-up multiplier (e.g., 1.25 for 25% gross-up).
        """
        mapping = {
            "CONVENTIONAL": self.conventional,
            "FHA": self.fha,
            "VA": self.va,
            "USDA": self.usda,
            "NON_QM": self.conventional,  # Non-QM typically follows conventional
        }
        return mapping.get(program_type.upper(), self.conventional)


@dataclass
class TrendingRules:
    """Declining income thresholds and trending analysis rules.

    When income is declining year-over-year, underwriters must use the lower
    of the two-year average or the most recent year. These thresholds control
    warning levels and automatic conservative calculation triggers.

    References:
        - FNMA B3-3.1-01: "If the trend in the amount of income is declining,
          the lender must use the most recent amount of income."
        - FNMA B3-3.1-02: Same declining-income logic for variable income.
    """

    declining_warning_pct: float = 10.0
    """Year-over-year decline percentage that triggers a warning flag.
    Below this threshold, income is considered stable."""

    declining_critical_pct: float = 20.0
    """Year-over-year decline percentage that triggers critical review.
    Income must be justified or the lower figure is used."""

    declining_severe_pct: float = 25.0
    """Year-over-year decline exceeding this threshold requires detailed
    explanation and may result in income being excluded entirely."""

    use_lower_when_declining: bool = True
    """When True, automatically use the lower of YTD-annualized vs. 2-year
    average when income is declining. Per FNMA guidelines."""

    commission_to_total_threshold_pct: float = 25.0
    """When commission income exceeds this percentage of total income,
    the borrower is treated as a commission-based earner with additional
    documentation requirements. FNMA B3-3.1-05."""


@dataclass
class RentalRules:
    """Rental income calculation rules by program type.

    Rental income is reduced by a vacancy/maintenance factor before being
    applied to qualifying income. The factor accounts for periods of vacancy,
    maintenance costs, and management expenses.

    References:
        - FNMA B3-3.1-09: 25% vacancy factor for Schedule E rental income.
          Net rental = (gross rents - PITIA) x 0.75, or Schedule E net / 12.
        - HUD 4000.1 II.A.4.d.(3)(b): FHA uses 25% vacancy factor but
          requires 2 years landlord experience. Conditional on property type.
        - VA Pamphlet 26-7 Ch. 9.18: VA uses 25% vacancy factor.
        - FNMA B3-3.1-09: New rental with no history uses 75% of market rent.
        - FNMA B3-3.1-09: Departing residence requires 6 months PITIA reserves.
    """

    vacancy_factor_conventional: float = 0.25
    """Vacancy/maintenance factor for conventional loans. 25% of gross rents
    are deducted (i.e., only 75% of gross rents count)."""

    vacancy_factor_fha: float = 0.25
    """Vacancy factor for FHA loans. 25% standard, but FHA has additional
    conditions: borrower must have 2 years landlord experience and property
    must not be a single-unit departing residence."""

    vacancy_factor_va: float = 0.25
    """Vacancy factor for VA loans. 25% per VA Pamphlet 26-7."""

    new_rental_market_rent_factor: float = 0.75
    """For properties with no rental history, use this factor times the
    appraiser's market rent estimate. FNMA B3-3.1-09: 75% of market rent."""

    departing_residence_reserve_months: int = 6
    """Months of PITIA reserves required when converting a primary residence
    to a rental property. FNMA B3-3.1-09."""

    def vacancy_factor_for_program(self, program_type: str) -> float:
        """Return the vacancy factor for a given program type.

        Args:
            program_type: One of CONVENTIONAL, FHA, VA, USDA, NON_QM.

        Returns:
            The vacancy factor (e.g., 0.25 means 25% deducted from gross rents).
        """
        mapping = {
            "CONVENTIONAL": self.vacancy_factor_conventional,
            "FHA": self.vacancy_factor_fha,
            "VA": self.vacancy_factor_va,
            "USDA": self.vacancy_factor_conventional,  # USDA follows conventional
            "NON_QM": self.vacancy_factor_conventional,
        }
        return mapping.get(program_type.upper(), self.vacancy_factor_conventional)


@dataclass
class ConfidenceRules:
    """AI confidence thresholds for automated review routing.

    These thresholds determine how income calculations are routed through
    the review workflow based on the AI confidence score (0-100).

    Higher thresholds are more conservative (more manual review).
    Lower thresholds allow more auto-approval (faster but riskier).
    """

    auto_approve: int = 98
    """Confidence score at or above which income can be auto-approved
    without human review. Only straightforward W-2 salary income
    typically reaches this threshold."""

    quick_review: int = 90
    """Confidence score at or above which income is routed to quick
    review (processor glance, no detailed audit required)."""

    standard_review: int = 80
    """Confidence score at or above which income gets standard processor
    review with basic verification."""

    detailed_review: int = 60
    """Confidence score at or above which income gets detailed
    underwriter review. Below this threshold, income requires
    senior underwriter or manager review."""


@dataclass
class BankStatementRules:
    """Non-QM bank statement program rules.

    Bank statement programs qualify self-employed borrowers using bank
    deposits instead of tax returns. An expense factor is applied to
    account for business expenses that reduce net qualifying income.

    Expense ratios vary by industry because different business types
    have fundamentally different cost structures.
    """

    personal_default_expense_factor: float = 0.50
    """Default expense factor for personal bank statement programs.
    50% of deposits are assumed to be business expenses."""

    business_service_expense_ratio: float = 0.50
    """Expense ratio for service-based businesses (consulting, legal, etc.).
    Service businesses typically have lower overhead."""

    business_retail_expense_ratio: float = 0.65
    """Expense ratio for retail businesses. Higher than service due to
    cost of goods sold (inventory, shipping)."""

    business_restaurant_expense_ratio: float = 0.70
    """Expense ratio for restaurant/food service businesses. Highest
    standard ratio due to food costs, labor, and overhead."""

    business_construction_expense_ratio: float = 0.60
    """Expense ratio for construction businesses. Materials and
    subcontractor costs drive higher expense ratios."""

    minimum_months: int = 12
    """Minimum months of bank statements required. Standard Non-QM
    programs require 12 or 24 months."""

    def expense_ratio_for_industry(self, industry: str) -> float:
        """Return the expense ratio for a given industry classification.

        Args:
            industry: Industry string (e.g., 'service', 'retail',
                'restaurant', 'construction'). Case-insensitive.

        Returns:
            Expense ratio as a float (e.g., 0.50 for 50%).
        """
        mapping = {
            "service": self.business_service_expense_ratio,
            "retail": self.business_retail_expense_ratio,
            "restaurant": self.business_restaurant_expense_ratio,
            "food": self.business_restaurant_expense_ratio,
            "construction": self.business_construction_expense_ratio,
        }
        return mapping.get(
            industry.lower().strip(),
            self.personal_default_expense_factor,
        )


# ---------------------------------------------------------------------------
# Master rule set
# ---------------------------------------------------------------------------

@dataclass
class InvestorRuleSet:
    """Complete set of income calculation rules for an investor/program.

    This is the top-level container that groups all rule categories for a
    specific investor or loan program type. Each calculation engine should
    accept an ``InvestorRuleSet`` and use its values instead of hardcoded
    constants.

    Usage::

        from services.income.investor_rules import get_rules_for_program

        rules = get_rules_for_program("FHA")
        vacancy = rules.rental.vacancy_factor_for_program("FHA")
        gross_up = rules.gross_up.for_program("FHA")

    Future: ``get_rules_for_investor("Wells Fargo", db=session)`` will query
    the ``investor_rule_configs`` table for overlay rules before falling back
    to program-type defaults.
    """

    investor_name: str = "Default (FNMA)"
    """Human-readable name of the investor or program."""

    program_type: str = "CONVENTIONAL"
    """Program type key: CONVENTIONAL, FHA, VA, USDA, NON_QM."""

    history: IncomeHistoryRules = field(default_factory=IncomeHistoryRules)
    """Documentation and history period requirements."""

    gross_up: GrossUpRules = field(default_factory=GrossUpRules)
    """Non-taxable income gross-up factors."""

    trending: TrendingRules = field(default_factory=TrendingRules)
    """Declining income thresholds and trending rules."""

    rental: RentalRules = field(default_factory=RentalRules)
    """Rental income vacancy factors and reserve requirements."""

    confidence: ConfidenceRules = field(default_factory=ConfidenceRules)
    """AI confidence thresholds for review routing."""

    bank_statement: BankStatementRules = field(default_factory=BankStatementRules)
    """Non-QM bank statement program rules."""


# ---------------------------------------------------------------------------
# Pre-built rule sets
# ---------------------------------------------------------------------------

FNMA_RULES = InvestorRuleSet(
    investor_name="Fannie Mae",
    program_type="CONVENTIONAL",
)
"""Fannie Mae conventional loan rules. This is the baseline -- all defaults
in the rule dataclasses reflect current FNMA Selling Guide requirements."""

FHA_RULES = InvestorRuleSet(
    investor_name="FHA",
    program_type="FHA",
    history=IncomeHistoryRules(
        rental_landlord_experience_years=2,
    ),
    # FHA vacancy factor is conditional on property type and landlord
    # experience, but the standard 25% factor applies in most cases.
    # The 2-year landlord experience requirement is the key FHA difference.
)
"""FHA loan rules. Key differences from FNMA:
- Requires 2 years landlord experience for rental income (HUD 4000.1).
- Vacancy factor is conditional on borrower experience and property type.
- Gross-up factor is the same 25% as conventional."""

VA_RULES = InvestorRuleSet(
    investor_name="VA",
    program_type="VA",
)
"""VA loan rules. Generally aligned with FNMA for income calculation.
VA has its own residual income requirement (not captured here -- that is
a separate DTI/qualification check, not an income calculation rule)."""

USDA_RULES = InvestorRuleSet(
    investor_name="USDA",
    program_type="USDA",
    gross_up=GrossUpRules(
        usda=1.0,
        conventional=1.0,
        fha=1.0,
        va=1.0,
    ),
)
"""USDA loan rules. Key difference: no gross-up of nontaxable income for
household income limit calculations. USDA uses actual (not grossed-up)
income to determine program eligibility. Some lenders allow gross-up for
repayment income; this defaults to the conservative no-gross-up approach."""

NON_QM_RULES = InvestorRuleSet(
    investor_name="Non-QM Default",
    program_type="NON_QM",
    history=IncomeHistoryRules(
        self_employment_tax_return_years=1,
        variable_income_history_months=12,
    ),
    confidence=ConfidenceRules(
        auto_approve=95,
    ),
)
"""Non-QM default rules. More lenient than agency:
- Only 1 year of tax returns for self-employment (vs. 2 for FNMA).
- 12 months variable income history (vs. 24 for FNMA).
- Lower auto-approve confidence threshold (95 vs. 98) since Non-QM
  has inherently more manual review built into the process."""

DEFAULT_RULES = FNMA_RULES
"""Default rule set used when no specific investor or program is specified.
Falls back to FNMA conventional rules as the industry baseline."""


# ---------------------------------------------------------------------------
# Rule set registry (program type -> pre-built rules)
# ---------------------------------------------------------------------------

_PROGRAM_RULES: Dict[str, InvestorRuleSet] = {
    "CONVENTIONAL": FNMA_RULES,
    "CONV": FNMA_RULES,
    "FNMA": FNMA_RULES,
    "FANNIE": FNMA_RULES,
    "FHLMC": FNMA_RULES,  # Freddie follows same income rules as Fannie
    "FREDDIE": FNMA_RULES,
    "FHA": FHA_RULES,
    "VA": VA_RULES,
    "USDA": USDA_RULES,
    "RD": USDA_RULES,  # Rural Development = USDA
    "NON_QM": NON_QM_RULES,
    "NONQM": NON_QM_RULES,
    "NON-QM": NON_QM_RULES,
    "BANK_STATEMENT": NON_QM_RULES,
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_rules_for_program(program_type: str) -> InvestorRuleSet:
    """Return the pre-built rule set for a given loan program type.

    This is a pure lookup against the pre-built rule sets -- no database
    access. Use this when you know the program type but not a specific
    investor overlay.

    Args:
        program_type: Loan program type string. Case-insensitive.
            Recognized values: CONVENTIONAL, CONV, FNMA, FANNIE, FHLMC,
            FREDDIE, FHA, VA, USDA, RD, NON_QM, NONQM, NON-QM,
            BANK_STATEMENT.

    Returns:
        The matching ``InvestorRuleSet``, or ``DEFAULT_RULES`` (FNMA)
        if the program type is not recognized.

    Examples::

        >>> rules = get_rules_for_program("FHA")
        >>> rules.history.rental_landlord_experience_years
        2

        >>> rules = get_rules_for_program("CONVENTIONAL")
        >>> rules.gross_up.for_program("CONVENTIONAL")
        1.25
    """
    normalized = program_type.strip().upper() if program_type else ""
    result = _PROGRAM_RULES.get(normalized)

    if result is None:
        logger.warning(
            "Unknown program type '%s', falling back to DEFAULT_RULES (FNMA)",
            program_type,
        )
        return DEFAULT_RULES

    return result


def get_rules_for_investor(
    investor_name: str,
    program_type: Optional[str] = None,
    db=None,
) -> InvestorRuleSet:
    """Return income calculation rules for a specific investor.

    This is the primary entry point for the rules engine. It implements
    a three-tier lookup:

    1. **Database lookup** (future): Query the ``investor_rule_configs``
       table for custom rules stored per-investor. Requires a ``db``
       session. Not yet implemented -- returns None from DB path.

    2. **Program type fallback**: If no database rules exist but a
       ``program_type`` is provided, return the pre-built rule set for
       that program type.

    3. **Default**: Return ``DEFAULT_RULES`` (FNMA conventional) if
       nothing else matches.

    Args:
        investor_name: Name of the investor (e.g., "Wells Fargo",
            "United Wholesale Mortgage", "Fannie Mae"). Used for
            database lookup and pre-built rule matching.
        program_type: Optional loan program type to use as fallback
            if no investor-specific rules are found in the database.
        db: Optional database session for querying custom rules.
            Pass ``None`` to skip database lookup entirely.

    Returns:
        The best matching ``InvestorRuleSet``.

    Examples::

        >>> # Simple lookup by investor name (matches pre-built)
        >>> rules = get_rules_for_investor("FHA")
        >>> rules.investor_name
        'FHA'

        >>> # Investor with program type fallback
        >>> rules = get_rules_for_investor("United Wholesale Mortgage",
        ...                                 program_type="CONVENTIONAL")
        >>> rules.investor_name
        'Fannie Mae'

        >>> # Unknown investor, no program type -- gets FNMA defaults
        >>> rules = get_rules_for_investor("Some Unknown Investor")
        >>> rules.investor_name
        'Default (FNMA)'
    """
    # ----- Tier 1: Database lookup (future) -----
    if db is not None:
        db_rules = _load_rules_from_database(investor_name, db)
        if db_rules is not None:
            logger.info(
                "Loaded custom rules for investor '%s' from database",
                investor_name,
            )
            return db_rules

    # ----- Tier 2: Match investor name against pre-built sets -----
    normalized_name = investor_name.strip().upper() if investor_name else ""

    # Direct name match against pre-built rule set investor names
    name_mapping: Dict[str, InvestorRuleSet] = {
        "FANNIE MAE": FNMA_RULES,
        "FNMA": FNMA_RULES,
        "FREDDIE MAC": FNMA_RULES,
        "FHLMC": FNMA_RULES,
        "FHA": FHA_RULES,
        "VA": VA_RULES,
        "USDA": USDA_RULES,
        "NON-QM": NON_QM_RULES,
        "NON_QM": NON_QM_RULES,
    }

    if normalized_name in name_mapping:
        return name_mapping[normalized_name]

    # ----- Tier 3: Fall back to program type -----
    if program_type:
        logger.info(
            "No investor-specific rules for '%s', falling back to program type '%s'",
            investor_name,
            program_type,
        )
        return get_rules_for_program(program_type)

    # ----- Tier 4: Default -----
    logger.info(
        "No rules found for investor '%s' (no program type provided), "
        "using DEFAULT_RULES (FNMA)",
        investor_name,
    )
    return DEFAULT_RULES


# ---------------------------------------------------------------------------
# Database integration (future)
# ---------------------------------------------------------------------------

def _load_rules_from_database(
    investor_name: str,
    db,
) -> Optional[InvestorRuleSet]:
    """Load custom investor rules from the database.

    This is a placeholder for future database-backed rule storage.
    When implemented, it will:

    1. Query the ``investor_rule_configs`` table for the given investor.
    2. Deserialize the stored JSON rule overrides.
    3. Merge overrides onto the base rule set for the investor's program type.
    4. Return the merged ``InvestorRuleSet``.

    The table schema (future) would look like::

        CREATE TABLE investor_rule_configs (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id UUID NOT NULL REFERENCES organizations(id),
            investor_name VARCHAR(255) NOT NULL,
            program_type VARCHAR(50) NOT NULL,
            rule_overrides JSONB NOT NULL DEFAULT '{}',
            is_active BOOLEAN NOT NULL DEFAULT true,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE(org_id, investor_name, program_type)
        );

    Args:
        investor_name: The investor to look up.
        db: Active SQLAlchemy database session.

    Returns:
        An ``InvestorRuleSet`` with custom overrides applied, or ``None``
        if no custom rules exist for this investor.
    """
    # TODO: Implement database lookup when investor_rule_configs table is created.
    # For now, always return None to fall through to pre-built rules.
    return None
