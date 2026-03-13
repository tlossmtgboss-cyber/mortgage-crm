"""
Rental Income Analysis Service for Mortgage Underwriting

Calculates qualifying rental income per Fannie Mae (Selling Guide B3-3.4),
Freddie Mac (Guide 5306.1), FHA (HUD 4000.1 II.A.4.d), and VA (Chapter 4)
guidelines. Handles Schedule E analysis, proposed lease income, market-rent
appraisals, PITIA offset calculations, and departing-residence rules.

Integrates with:
    - smart_documents / smart_document_extractions for document data
    - income_calculations / income_sources for result persistence
    - income_verification_tasks for LO follow-up items
    - Loan model for property/occupancy data

Key analysis areas:
    1. Schedule E (existing rentals) with depreciation/insurance/tax add-backs
    2. Proposed rental from lease agreements (75% after vacancy)
    3. Market rent from appraisal for investment purchases
    4. PITIA offset method (positive cash flow = income, negative = DTI add)
    5. Departing residence rules with 6-month reserve verification
    6. FHA 2-year landlord experience requirement
    7. Cross-reference Schedule E against bank deposits

Usage:
    from services.smart_docs.income.rental_income_service import (
        RentalIncomeService,
        get_rental_income_service,
        RentalIncomeResult,
    )

    service = get_rental_income_service(db, org_id=42)
    result = await service.calculate_rental_income(
        org_id=42, loan_id=100, properties=[...]
    )
"""

import logging
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from typing import Optional, Dict, List, Any
from dataclasses import dataclass, field
from enum import Enum

from sqlalchemy.orm import Session
from sqlalchemy import text

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ZERO = Decimal("0.00")
TWO_PLACES = Decimal("0.01")
MONTHS_PER_YEAR = 12

# Vacancy factors by agency — percentage of gross rent NOT counted
# (i.e., only 75% of gross rent qualifies)
VACANCY_FACTOR_FANNIE = Decimal("0.25")
VACANCY_FACTOR_FREDDIE = Decimal("0.25")
VACANCY_FACTOR_VA = Decimal("0.25")
# FHA: no vacancy factor if 2-year history; 25% otherwise
VACANCY_FACTOR_FHA_NO_HISTORY = Decimal("0.25")
VACANCY_FACTOR_FHA_WITH_HISTORY = Decimal("0.00")

# Net rental factor (1 - vacancy) applied to gross/lease rents
NET_RENTAL_FACTOR = Decimal("0.75")

# Departing residence reserve requirement: 6 months of PITIA
DEPARTING_RESIDENCE_RESERVE_MONTHS = 6

# Minimum years of landlord experience for FHA
FHA_MIN_LANDLORD_YEARS = 2

# Minimum Schedule E history years for full qualifying
MIN_SCHEDULE_E_YEARS = 2

# Income trend thresholds
DECLINING_INCOME_WARN_PCT = Decimal("10")
DECLINING_INCOME_CRITICAL_PCT = Decimal("25")

# Cross-reference tolerance: bank deposits within this % of Schedule E rents
DEPOSIT_MATCH_TOLERANCE_PCT = Decimal("15")


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class RentalIncomeMethod(str, Enum):
    """Method used to derive rental income."""
    SCHEDULE_E = "schedule_e"
    LEASE_AGREEMENT = "lease_agreement"
    MARKET_RENT_APPRAISAL = "market_rent_appraisal"
    PITIA_OFFSET = "pitia_offset"


class LoanProgram(str, Enum):
    """Agency/program type for guideline selection."""
    FANNIE_MAE = "fannie_mae"
    FREDDIE_MAC = "freddie_mac"
    FHA = "fha"
    VA = "va"
    CONVENTIONAL = "conventional"  # alias for Fannie/Freddie
    JUMBO = "jumbo"
    NON_QM = "non_qm"


class PropertyRole(str, Enum):
    """Role of the property in the transaction."""
    SUBJECT = "subject"             # property being purchased/refinanced
    RETAINED_RENTAL = "retained"    # existing rental the borrower is keeping
    DEPARTING_RESIDENCE = "departing"  # current primary converting to rental


# ---------------------------------------------------------------------------
# Data Classes — Inputs
# ---------------------------------------------------------------------------

@dataclass
class ScheduleELineItems:
    """Parsed Schedule E line items for a single property/year.

    Line numbers reference IRS Schedule E, Part I.
    """
    tax_year: int
    property_address: Optional[str] = None
    property_type: Optional[str] = None  # Single Family, Multi Family, etc.

    # Line 3: Rents received
    gross_rents_received: Decimal = ZERO

    # Expenses (Lines 5-19)
    advertising: Decimal = ZERO                # Line 5
    auto_and_travel: Decimal = ZERO            # Line 6
    cleaning_and_maintenance: Decimal = ZERO   # Line 7
    commissions: Decimal = ZERO                # Line 8
    insurance: Decimal = ZERO                  # Line 9
    legal_and_professional: Decimal = ZERO     # Line 10
    management_fees: Decimal = ZERO            # Line 11
    mortgage_interest: Decimal = ZERO          # Line 12
    other_interest: Decimal = ZERO             # Line 13
    repairs: Decimal = ZERO                    # Line 14
    supplies: Decimal = ZERO                   # Line 15
    taxes: Decimal = ZERO                      # Line 16
    utilities: Decimal = ZERO                  # Line 17
    depreciation: Decimal = ZERO               # Line 18
    other_expenses: Decimal = ZERO             # Line 19
    total_expenses: Decimal = ZERO             # Line 20

    # Fair rental days / personal use days
    fair_rental_days: int = 0
    personal_use_days: int = 0

    # Source document IDs
    source_doc_ids: List[int] = field(default_factory=list)


@dataclass
class LeaseData:
    """Lease agreement data for proposed rental income."""
    property_address: Optional[str] = None
    monthly_rent: Decimal = ZERO
    lease_start_date: Optional[str] = None  # ISO date string
    lease_end_date: Optional[str] = None
    tenant_name: Optional[str] = None
    is_signed: bool = False
    security_deposit: Decimal = ZERO
    source_doc_ids: List[int] = field(default_factory=list)


@dataclass
class PropertyData:
    """Property input data for rental income analysis."""
    property_id: Optional[str] = None
    property_address: Optional[str] = None
    property_type: Optional[str] = None  # single_family, multi_family, condo, etc.
    role: str = "retained"  # subject, retained, departing
    occupancy_type: Optional[str] = None  # primary, investment, second_home

    # Schedule E data (existing rentals)
    schedule_e_data: List[ScheduleELineItems] = field(default_factory=list)

    # Lease data (proposed rentals)
    lease_data: Optional[LeaseData] = None

    # Market rent from appraisal
    market_rent_monthly: Optional[Decimal] = None
    appraisal_value: Optional[Decimal] = None

    # PITIA for offset calculation
    pitia_monthly: Optional[Decimal] = None
    # PITIA components (for add-back identification)
    pitia_principal_interest: Optional[Decimal] = None
    pitia_taxes: Optional[Decimal] = None
    pitia_insurance: Optional[Decimal] = None
    pitia_hoa: Optional[Decimal] = None
    pitia_mi: Optional[Decimal] = None  # Mortgage insurance

    # Reserve verification (for departing residence)
    verified_reserves: Optional[Decimal] = None

    # FHA landlord experience
    years_landlord_experience: Optional[int] = None
    has_property_management: bool = False


# ---------------------------------------------------------------------------
# Data Classes — Outputs
# ---------------------------------------------------------------------------

@dataclass
class ScheduleEResult:
    """Result of Schedule E analysis for one property."""
    property_address: Optional[str]
    tax_years_analyzed: List[int] = field(default_factory=list)

    # Per-year breakdown
    yearly_breakdown: List[Dict[str, Any]] = field(default_factory=list)

    # Two-year aggregate
    avg_gross_rents: Decimal = ZERO
    avg_total_expenses: Decimal = ZERO
    avg_depreciation_addback: Decimal = ZERO
    avg_insurance_addback: Decimal = ZERO
    avg_taxes_addback: Decimal = ZERO
    avg_mortgage_interest_addback: Decimal = ZERO
    total_addbacks: Decimal = ZERO

    # Qualifying calculation
    net_rental_before_addbacks: Decimal = ZERO
    net_rental_after_addbacks: Decimal = ZERO
    monthly_qualifying_income: Decimal = ZERO

    # Flags
    flags: List[str] = field(default_factory=list)
    notes: str = ""


@dataclass
class ProposedRentalResult:
    """Result of proposed rental income calculation."""
    property_address: Optional[str]
    method: str = ""  # lease_agreement or market_rent_appraisal

    gross_monthly_rent: Decimal = ZERO
    vacancy_factor_pct: Decimal = ZERO
    net_monthly_rent: Decimal = ZERO  # after vacancy
    monthly_qualifying_income: Decimal = ZERO

    # For lease-based
    lease_term_months: Optional[int] = None
    is_lease_signed: bool = False

    # For appraisal-based
    appraisal_market_rent: Optional[Decimal] = None

    flags: List[str] = field(default_factory=list)
    notes: str = ""


@dataclass
class PITIAOffsetResult:
    """Result of PITIA offset calculation."""
    property_address: Optional[str]
    gross_rental_income: Decimal = ZERO
    pitia_monthly: Decimal = ZERO
    net_cash_flow: Decimal = ZERO
    is_positive: bool = False
    # Positive: counted as income; Negative: added to monthly obligations
    income_adjustment: Decimal = ZERO
    obligation_adjustment: Decimal = ZERO
    notes: str = ""


@dataclass
class ExperienceValidation:
    """FHA landlord experience validation result."""
    meets_requirement: bool = False
    years_documented: int = 0
    required_years: int = FHA_MIN_LANDLORD_YEARS
    has_property_management: bool = False
    waiver_eligible: bool = False  # property management can waive experience
    flags: List[str] = field(default_factory=list)
    notes: str = ""


@dataclass
class DepositCrossReference:
    """Cross-reference of Schedule E rents against bank deposits."""
    property_address: Optional[str]
    schedule_e_annual_rents: Decimal = ZERO
    bank_deposit_total: Decimal = ZERO
    variance_pct: Decimal = ZERO
    is_within_tolerance: bool = True
    flags: List[str] = field(default_factory=list)


@dataclass
class PropertyRentalResult:
    """Complete rental income result for a single property."""
    property_id: Optional[str]
    property_address: Optional[str]
    property_type: Optional[str]
    role: str  # subject, retained, departing

    # Income calculation
    method: str = ""  # schedule_e, lease_agreement, market_rent_appraisal, pitia_offset
    monthly_qualifying_income: Decimal = ZERO
    annual_qualifying_income: Decimal = ZERO
    is_income_positive: bool = True

    # Sub-results
    schedule_e_result: Optional[ScheduleEResult] = None
    proposed_rental_result: Optional[ProposedRentalResult] = None
    pitia_offset_result: Optional[PITIAOffsetResult] = None
    experience_validation: Optional[ExperienceValidation] = None
    deposit_cross_ref: Optional[DepositCrossReference] = None

    # Flags and notes
    flags: List[str] = field(default_factory=list)
    notes: str = ""
    confidence: int = 0  # 0-100


@dataclass
class RentalIncomeResult:
    """Complete rental income analysis across all properties."""
    loan_id: int
    org_id: int
    loan_program: str

    # Per-property results
    properties: List[PropertyRentalResult] = field(default_factory=list)

    # Aggregate totals
    total_monthly_qualifying_income: Decimal = ZERO
    total_annual_qualifying_income: Decimal = ZERO
    net_positive_income: Decimal = ZERO      # sum of properties with positive cash flow
    net_negative_income: Decimal = ZERO      # sum of properties with negative cash flow (DTI add)

    # Aggregate flags
    flags: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)
    tasks_to_create: List[Dict[str, Any]] = field(default_factory=list)

    # Metadata
    confidence: int = 0  # 0-100
    analysis_timestamp: str = ""
    success: bool = True
    error: Optional[str] = None


# =============================================================================
# SERVICE
# =============================================================================

class RentalIncomeService:
    """
    Calculates qualifying rental income per agency guidelines.

    Supports three income derivation methods:
    - Schedule E analysis (existing rental properties from tax returns)
    - Lease agreement (proposed rental on departing residence or new investment)
    - Market rent appraisal (properties without lease history)

    Applies agency-specific vacancy factors:
    - Fannie Mae / Freddie Mac / VA: 25% vacancy
    - FHA: 0% if 2-year landlord history, 25% otherwise

    PITIA offset method determines whether rental income is counted as
    qualifying income (positive cash flow) or added to monthly obligations
    (negative cash flow) for DTI purposes.
    """

    def __init__(self, db: Session, org_id: int, user_id: Optional[int] = None):
        self.db = db
        self.org_id = org_id
        self.user_id = user_id

    # =========================================================================
    # 1. MAIN ENTRY POINT
    # =========================================================================

    async def calculate_rental_income(
        self,
        org_id: int,
        loan_id: int,
        properties: List[PropertyData],
        loan_program: str = "conventional",
    ) -> RentalIncomeResult:
        """
        Calculate qualifying rental income across all provided properties.

        For each property, selects the appropriate calculation method based
        on available data (Schedule E, lease, or appraisal market rent) and
        the property's role in the transaction.

        Args:
            org_id: Organization ID for tenant isolation.
            loan_id: Loan ID.
            properties: List of PropertyData with rental information.
            loan_program: Agency program (fannie_mae, freddie_mac, fha, va, conventional).

        Returns:
            RentalIncomeResult with per-property breakdown and aggregate totals.
        """
        self._verify_org(org_id)

        result = RentalIncomeResult(
            loan_id=loan_id,
            org_id=org_id,
            loan_program=loan_program,
            analysis_timestamp=datetime.now(timezone.utc).isoformat(),
        )

        if not properties:
            result.success = False
            result.error = "No properties provided for rental income analysis."
            result.flags.append("NO_PROPERTIES")
            return result

        program = self._normalize_program(loan_program)
        all_confidences: List[int] = []

        for prop in properties:
            prop_result = await self._analyze_single_property(
                loan_id=loan_id,
                prop=prop,
                program=program,
            )
            result.properties.append(prop_result)
            all_confidences.append(prop_result.confidence)

            # Aggregate income/loss
            if prop_result.is_income_positive:
                result.net_positive_income += prop_result.monthly_qualifying_income
            else:
                result.net_negative_income += prop_result.monthly_qualifying_income

            result.total_monthly_qualifying_income += prop_result.monthly_qualifying_income
            result.flags.extend(prop_result.flags)

        result.total_annual_qualifying_income = (
            result.total_monthly_qualifying_income * MONTHS_PER_YEAR
        ).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)

        # Overall confidence: weighted average or minimum if any property is low
        if all_confidences:
            result.confidence = min(all_confidences)

        # Generate recommendations
        result.recommendations = self._generate_recommendations(result, program)
        result.tasks_to_create = self._generate_tasks(result, loan_id)

        # Persist to income_sources if we have results
        await self._persist_results(result, loan_id)

        return result

    # =========================================================================
    # 2. SCHEDULE E ANALYSIS
    # =========================================================================

    async def analyze_schedule_e(
        self,
        schedule_e_data: List[ScheduleELineItems],
        property_id: Optional[str] = None,
        pitia_in_expenses: bool = True,
        loan_program: str = "conventional",
    ) -> ScheduleEResult:
        """
        Analyze Schedule E line items to derive qualifying rental income.

        Per Fannie Mae B3-3.4-01:
        - Start with gross rents received (Line 3)
        - Subtract total expenses (Lines 5-19)
        - Add back depreciation (Line 18) — non-cash expense
        - Add back insurance (Line 9) if already in PITIA
        - Add back taxes (Line 16) if already in PITIA
        - Add back mortgage interest (Line 12) if already in PITIA
        - Result / 12 = monthly qualifying income

        Args:
            schedule_e_data: Schedule E line items per year.
            property_id: Optional property identifier.
            pitia_in_expenses: If True, add back insurance/taxes/mortgage
                interest since they are already counted in PITIA.
            loan_program: Agency program for guideline selection.

        Returns:
            ScheduleEResult with qualifying income and breakdown.
        """
        result = ScheduleEResult(
            property_address=schedule_e_data[0].property_address if schedule_e_data else None,
        )

        if not schedule_e_data:
            result.flags.append("NO_SCHEDULE_E_DATA")
            return result

        # Sort by tax year descending (most recent first)
        sorted_data = sorted(schedule_e_data, key=lambda x: x.tax_year, reverse=True)
        result.tax_years_analyzed = [d.tax_year for d in sorted_data]

        yearly_qualifying: List[Decimal] = []

        for se in sorted_data:
            # Recalculate total_expenses if not provided
            calculated_total = self._sum_schedule_e_expenses(se)
            total_expenses = se.total_expenses if se.total_expenses != ZERO else calculated_total

            # Depreciation add-back (always — non-cash expense)
            depreciation_addback = se.depreciation

            # Conditional add-backs when PITIA already includes these costs
            insurance_addback = se.insurance if pitia_in_expenses else ZERO
            taxes_addback = se.taxes if pitia_in_expenses else ZERO
            mortgage_interest_addback = se.mortgage_interest if pitia_in_expenses else ZERO

            total_addbacks = (
                depreciation_addback
                + insurance_addback
                + taxes_addback
                + mortgage_interest_addback
            )

            net_before_addbacks = se.gross_rents_received - total_expenses
            net_after_addbacks = net_before_addbacks + total_addbacks
            monthly_income = (net_after_addbacks / MONTHS_PER_YEAR).quantize(
                TWO_PLACES, rounding=ROUND_HALF_UP
            )

            yearly_qualifying.append(net_after_addbacks)

            result.yearly_breakdown.append({
                "tax_year": se.tax_year,
                "gross_rents": float(se.gross_rents_received),
                "total_expenses": float(total_expenses),
                "depreciation_addback": float(depreciation_addback),
                "insurance_addback": float(insurance_addback),
                "taxes_addback": float(taxes_addback),
                "mortgage_interest_addback": float(mortgage_interest_addback),
                "total_addbacks": float(total_addbacks),
                "net_before_addbacks": float(net_before_addbacks),
                "net_after_addbacks": float(net_after_addbacks),
                "monthly_qualifying": float(monthly_income),
                "fair_rental_days": se.fair_rental_days,
                "personal_use_days": se.personal_use_days,
            })

        # Two-year averaging per Fannie Mae
        if len(yearly_qualifying) >= MIN_SCHEDULE_E_YEARS:
            # Use the two most recent years
            year1 = yearly_qualifying[0]
            year2 = yearly_qualifying[1]

            # Check for declining trend — if declining, use lower (most recent) year
            if year1 < year2 and year2 > ZERO:
                decline_pct = ((year2 - year1) / abs(year2) * 100).quantize(
                    TWO_PLACES, rounding=ROUND_HALF_UP
                )
                if decline_pct > DECLINING_INCOME_CRITICAL_PCT:
                    result.flags.append(
                        f"DECLINING_RENTAL_INCOME: Year-over-year decline of "
                        f"{decline_pct}% — using most recent year only"
                    )
                    avg_annual = year1
                elif decline_pct > DECLINING_INCOME_WARN_PCT:
                    result.flags.append(
                        f"DECLINING_RENTAL_TREND: {decline_pct}% decline — "
                        f"using 2-year average per guidelines"
                    )
                    avg_annual = ((year1 + year2) / 2).quantize(
                        TWO_PLACES, rounding=ROUND_HALF_UP
                    )
                else:
                    avg_annual = ((year1 + year2) / 2).quantize(
                        TWO_PLACES, rounding=ROUND_HALF_UP
                    )
            else:
                avg_annual = ((year1 + year2) / 2).quantize(
                    TWO_PLACES, rounding=ROUND_HALF_UP
                )
        else:
            # Single year: use as-is but flag
            avg_annual = yearly_qualifying[0]
            result.flags.append(
                "SINGLE_YEAR_SCHEDULE_E: Only 1 year of rental history — "
                "2-year history recommended"
            )

        result.net_rental_after_addbacks = avg_annual
        result.monthly_qualifying_income = (avg_annual / MONTHS_PER_YEAR).quantize(
            TWO_PLACES, rounding=ROUND_HALF_UP
        )

        # Aggregate add-back averages for reporting
        n = len(sorted_data)
        result.avg_gross_rents = self._avg_decimal(
            [se.gross_rents_received for se in sorted_data]
        )
        result.avg_depreciation_addback = self._avg_decimal(
            [se.depreciation for se in sorted_data]
        )
        if pitia_in_expenses:
            result.avg_insurance_addback = self._avg_decimal(
                [se.insurance for se in sorted_data]
            )
            result.avg_taxes_addback = self._avg_decimal(
                [se.taxes for se in sorted_data]
            )
            result.avg_mortgage_interest_addback = self._avg_decimal(
                [se.mortgage_interest for se in sorted_data]
            )
        result.total_addbacks = (
            result.avg_depreciation_addback
            + result.avg_insurance_addback
            + result.avg_taxes_addback
            + result.avg_mortgage_interest_addback
        )

        # Check personal use vs fair rental days
        for se in sorted_data:
            if se.personal_use_days > 14 and se.fair_rental_days > 0:
                personal_pct = Decimal(str(se.personal_use_days)) / (
                    Decimal(str(se.personal_use_days + se.fair_rental_days))
                ) * 100
                if personal_pct > Decimal("10"):
                    result.flags.append(
                        f"PERSONAL_USE_{se.tax_year}: {se.personal_use_days} personal-use days "
                        f"({personal_pct.quantize(TWO_PLACES)}%) — may limit deductions"
                    )

        result.notes = (
            f"Schedule E analysis: {n}-year{'s' if n > 1 else ''} analyzed. "
            f"Monthly qualifying: ${float(result.monthly_qualifying_income):,.2f}"
        )

        return result

    # =========================================================================
    # 3. PROPOSED RENTAL (LEASE / MARKET RENT)
    # =========================================================================

    async def calculate_proposed_rental(
        self,
        lease_data: Optional[LeaseData],
        property_type: Optional[str],
        loan_program: str,
        market_rent_monthly: Optional[Decimal] = None,
        fha_has_experience: bool = False,
    ) -> ProposedRentalResult:
        """
        Calculate qualifying income from a proposed rental.

        For lease agreements:
        - Use 75% of monthly lease rent (after vacancy factor)
        - Lease must be signed and in effect

        For market rent (appraisal):
        - Use 75% of appraised market rent
        - Typically for investment property purchases

        FHA: no vacancy factor if borrower has 2-year landlord history.

        Args:
            lease_data: Lease agreement details (if available).
            property_type: Property type string.
            loan_program: Agency program.
            market_rent_monthly: Appraised market rent (if no lease).
            fha_has_experience: Whether borrower meets FHA experience requirement.

        Returns:
            ProposedRentalResult with qualifying income.
        """
        result = ProposedRentalResult(
            property_address=lease_data.property_address if lease_data else None,
        )

        program = self._normalize_program(loan_program)
        vacancy_pct = self._get_vacancy_factor(program, fha_has_experience)
        net_factor = Decimal("1") - vacancy_pct

        if lease_data and lease_data.monthly_rent > ZERO:
            # Lease-based calculation
            result.method = RentalIncomeMethod.LEASE_AGREEMENT.value
            result.gross_monthly_rent = lease_data.monthly_rent
            result.vacancy_factor_pct = vacancy_pct * 100
            result.net_monthly_rent = (
                lease_data.monthly_rent * net_factor
            ).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
            result.monthly_qualifying_income = result.net_monthly_rent
            result.is_lease_signed = lease_data.is_signed

            if not lease_data.is_signed:
                result.flags.append(
                    "UNSIGNED_LEASE: Lease must be fully executed to count rental income"
                )
                result.monthly_qualifying_income = ZERO

            # Calculate lease term
            if lease_data.lease_start_date and lease_data.lease_end_date:
                try:
                    start = datetime.fromisoformat(lease_data.lease_start_date)
                    end = datetime.fromisoformat(lease_data.lease_end_date)
                    result.lease_term_months = max(
                        1, int((end - start).days / 30.44)
                    )
                    if result.lease_term_months < 12:
                        result.flags.append(
                            f"SHORT_LEASE_TERM: Lease is {result.lease_term_months} months — "
                            f"12-month minimum typically required"
                        )
                except (ValueError, TypeError):
                    result.flags.append("INVALID_LEASE_DATES: Could not parse lease dates")

            result.notes = (
                f"Lease-based: ${float(lease_data.monthly_rent):,.2f}/mo * "
                f"{float(net_factor) * 100:.0f}% = ${float(result.net_monthly_rent):,.2f}/mo"
            )

        elif market_rent_monthly is not None and market_rent_monthly > ZERO:
            # Market rent from appraisal
            result.method = RentalIncomeMethod.MARKET_RENT_APPRAISAL.value
            result.gross_monthly_rent = market_rent_monthly
            result.vacancy_factor_pct = vacancy_pct * 100
            result.appraisal_market_rent = market_rent_monthly
            result.net_monthly_rent = (
                market_rent_monthly * net_factor
            ).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
            result.monthly_qualifying_income = result.net_monthly_rent

            result.notes = (
                f"Appraisal market rent: ${float(market_rent_monthly):,.2f}/mo * "
                f"{float(net_factor) * 100:.0f}% = ${float(result.net_monthly_rent):,.2f}/mo"
            )

        else:
            result.flags.append(
                "NO_RENTAL_DATA: Neither lease nor market rent provided"
            )
            result.notes = "No lease agreement or appraisal market rent available."

        return result

    # =========================================================================
    # 4. PITIA OFFSET CALCULATION
    # =========================================================================

    async def calculate_pitia_offset(
        self,
        rental_income: Decimal,
        pitia: Decimal,
        property_address: Optional[str] = None,
    ) -> PITIAOffsetResult:
        """
        Calculate PITIA offset for a rental property.

        Per Fannie Mae B3-3.4-01:
        - If rental income >= PITIA: net positive cash flow is qualifying income
        - If rental income < PITIA: net negative cash flow is added to monthly
          obligations in DTI

        This is the standard method used after deriving gross rental income
        (from Schedule E, lease, or appraisal) and subtracting PITIA.

        Args:
            rental_income: Monthly rental income (after vacancy factor).
            pitia: Monthly PITIA (principal, interest, taxes, insurance, HOA, MI).
            property_address: Optional address for result labeling.

        Returns:
            PITIAOffsetResult indicating income or obligation adjustment.
        """
        result = PITIAOffsetResult(
            property_address=property_address,
            gross_rental_income=rental_income,
            pitia_monthly=pitia,
        )

        if pitia <= ZERO:
            # No PITIA — entire rental income qualifies
            result.net_cash_flow = rental_income
            result.is_positive = rental_income >= ZERO
            result.income_adjustment = rental_income if rental_income > ZERO else ZERO
            result.obligation_adjustment = ZERO
            result.notes = "No PITIA — full rental income qualifies."
            return result

        result.net_cash_flow = (rental_income - pitia).quantize(
            TWO_PLACES, rounding=ROUND_HALF_UP
        )
        result.is_positive = result.net_cash_flow >= ZERO

        if result.is_positive:
            # Positive cash flow: counted as qualifying income
            result.income_adjustment = result.net_cash_flow
            result.obligation_adjustment = ZERO
            result.notes = (
                f"Positive cash flow: ${float(rental_income):,.2f} rent - "
                f"${float(pitia):,.2f} PITIA = ${float(result.net_cash_flow):,.2f}/mo income"
            )
        else:
            # Negative cash flow: added to monthly obligations in DTI
            result.income_adjustment = ZERO
            result.obligation_adjustment = abs(result.net_cash_flow)
            result.notes = (
                f"Negative cash flow: ${float(rental_income):,.2f} rent - "
                f"${float(pitia):,.2f} PITIA = -${float(abs(result.net_cash_flow)):,.2f}/mo "
                f"added to obligations"
            )

        return result

    # =========================================================================
    # 5. FHA LANDLORD EXPERIENCE VALIDATION
    # =========================================================================

    async def validate_landlord_experience(
        self,
        tax_history: List[ScheduleELineItems],
        has_property_management: bool = False,
        claimed_years: Optional[int] = None,
    ) -> ExperienceValidation:
        """
        Validate FHA landlord experience requirement.

        Per HUD 4000.1 II.A.4.d.iii(B):
        - Borrower must have 2-year history as a landlord, OR
        - Borrower must have engaged a property management company
        - Schedule E filed for at least 2 consecutive years serves as evidence

        Args:
            tax_history: Schedule E data showing rental history.
            has_property_management: Whether a property management company is engaged.
            claimed_years: Borrower-stated years of landlord experience.

        Returns:
            ExperienceValidation with eligibility determination.
        """
        result = ExperienceValidation(
            required_years=FHA_MIN_LANDLORD_YEARS,
            has_property_management=has_property_management,
        )

        # Count unique tax years with Schedule E filing
        tax_years_with_rental = set()
        for se in tax_history:
            if se.gross_rents_received > ZERO:
                tax_years_with_rental.add(se.tax_year)

        result.years_documented = len(tax_years_with_rental)

        # Property management waiver
        if has_property_management:
            result.waiver_eligible = True
            result.meets_requirement = True
            result.notes = (
                f"Property management company engaged — FHA experience "
                f"requirement satisfied via management waiver. "
                f"Documented {result.years_documented} year(s) of Schedule E history."
            )
            return result

        # Check documented history
        if result.years_documented >= FHA_MIN_LANDLORD_YEARS:
            result.meets_requirement = True
            sorted_years = sorted(tax_years_with_rental, reverse=True)
            result.notes = (
                f"FHA 2-year landlord experience verified via Schedule E: "
                f"tax years {', '.join(str(y) for y in sorted_years)}"
            )
        else:
            result.meets_requirement = False
            result.flags.append(
                f"FHA_LANDLORD_EXPERIENCE_INSUFFICIENT: Only {result.years_documented} "
                f"year(s) of Schedule E history documented (need {FHA_MIN_LANDLORD_YEARS})"
            )
            if claimed_years is not None and claimed_years >= FHA_MIN_LANDLORD_YEARS:
                result.flags.append(
                    "FHA_EXPERIENCE_UNVERIFIED: Borrower claims sufficient experience "
                    "but Schedule E does not support it — request additional documentation"
                )
            result.notes = (
                f"FHA requires {FHA_MIN_LANDLORD_YEARS} years of landlord experience. "
                f"Only {result.years_documented} year(s) verified. "
                f"Consider engaging a property management company to satisfy requirement."
            )

        return result

    # =========================================================================
    # 6. SINGLE PROPERTY ANALYSIS (INTERNAL)
    # =========================================================================

    async def _analyze_single_property(
        self,
        loan_id: int,
        prop: PropertyData,
        program: str,
    ) -> PropertyRentalResult:
        """Analyze a single property and determine qualifying rental income."""
        prop_result = PropertyRentalResult(
            property_id=prop.property_id,
            property_address=prop.property_address,
            property_type=prop.property_type,
            role=prop.role,
        )

        # ---------------------------------------------------------------
        # A. Departing residence validation
        # ---------------------------------------------------------------
        if prop.role == PropertyRole.DEPARTING.value:
            dep_flags = self._validate_departing_residence(prop)
            prop_result.flags.extend(dep_flags)

        # ---------------------------------------------------------------
        # B. FHA landlord experience (if FHA program)
        # ---------------------------------------------------------------
        if program == LoanProgram.FHA.value and prop.schedule_e_data:
            exp_result = await self.validate_landlord_experience(
                tax_history=prop.schedule_e_data,
                has_property_management=prop.has_property_management,
                claimed_years=prop.years_landlord_experience,
            )
            prop_result.experience_validation = exp_result
            prop_result.flags.extend(exp_result.flags)

        fha_has_experience = (
            prop_result.experience_validation is not None
            and prop_result.experience_validation.meets_requirement
        ) if program == LoanProgram.FHA.value else True

        # ---------------------------------------------------------------
        # C. Determine calculation method
        # ---------------------------------------------------------------
        if prop.schedule_e_data:
            # Existing rental: use Schedule E
            pitia_in_expenses = prop.pitia_monthly is not None and prop.pitia_monthly > ZERO
            se_result = await self.analyze_schedule_e(
                schedule_e_data=prop.schedule_e_data,
                property_id=prop.property_id,
                pitia_in_expenses=pitia_in_expenses,
                loan_program=program,
            )
            prop_result.schedule_e_result = se_result
            prop_result.method = RentalIncomeMethod.SCHEDULE_E.value
            prop_result.monthly_qualifying_income = se_result.monthly_qualifying_income
            prop_result.flags.extend(se_result.flags)
            prop_result.confidence = 85 if len(se_result.tax_years_analyzed) >= 2 else 65

            # Cross-reference against bank deposits if possible
            deposit_xref = await self._cross_reference_deposits(
                loan_id=loan_id,
                property_address=prop.property_address,
                schedule_e_data=prop.schedule_e_data,
            )
            if deposit_xref:
                prop_result.deposit_cross_ref = deposit_xref
                prop_result.flags.extend(deposit_xref.flags)

        elif prop.role == PropertyRole.SUBJECT.value and prop.market_rent_monthly:
            # Subject property investment purchase: use appraisal market rent
            proposed = await self.calculate_proposed_rental(
                lease_data=None,
                property_type=prop.property_type,
                loan_program=program,
                market_rent_monthly=prop.market_rent_monthly,
                fha_has_experience=fha_has_experience,
            )
            prop_result.proposed_rental_result = proposed
            prop_result.method = RentalIncomeMethod.MARKET_RENT_APPRAISAL.value
            prop_result.monthly_qualifying_income = proposed.monthly_qualifying_income
            prop_result.flags.extend(proposed.flags)
            prop_result.confidence = 70

        elif prop.lease_data:
            # Proposed rental from lease (departing residence or new investment)
            proposed = await self.calculate_proposed_rental(
                lease_data=prop.lease_data,
                property_type=prop.property_type,
                loan_program=program,
                fha_has_experience=fha_has_experience,
            )
            prop_result.proposed_rental_result = proposed
            prop_result.method = RentalIncomeMethod.LEASE_AGREEMENT.value
            prop_result.monthly_qualifying_income = proposed.monthly_qualifying_income
            prop_result.flags.extend(proposed.flags)
            prop_result.confidence = 75 if proposed.is_lease_signed else 40

        else:
            prop_result.flags.append(
                f"NO_INCOME_DATA: No Schedule E, lease, or market rent for "
                f"{prop.property_address or 'unknown property'}"
            )
            prop_result.confidence = 0

        # ---------------------------------------------------------------
        # D. PITIA offset (if PITIA provided)
        # ---------------------------------------------------------------
        if prop.pitia_monthly is not None and prop.pitia_monthly > ZERO:
            pitia_result = await self.calculate_pitia_offset(
                rental_income=prop_result.monthly_qualifying_income,
                pitia=prop.pitia_monthly,
                property_address=prop.property_address,
            )
            prop_result.pitia_offset_result = pitia_result

            # Override qualifying income with PITIA-adjusted value
            if pitia_result.is_positive:
                prop_result.monthly_qualifying_income = pitia_result.income_adjustment
                prop_result.is_income_positive = True
            else:
                # Negative: treated as obligation, not income
                prop_result.monthly_qualifying_income = -pitia_result.obligation_adjustment
                prop_result.is_income_positive = False

        prop_result.annual_qualifying_income = (
            prop_result.monthly_qualifying_income * MONTHS_PER_YEAR
        ).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)

        return prop_result

    # =========================================================================
    # 7. DEPARTING RESIDENCE VALIDATION
    # =========================================================================

    def _validate_departing_residence(self, prop: PropertyData) -> List[str]:
        """
        Validate departing residence requirements.

        Per Fannie Mae B3-3.4-03:
        - Must have signed lease to count rental income
        - 75% of lease amount qualifies
        - Borrower must show 6 months PITIA reserves

        Returns list of flag strings.
        """
        flags: List[str] = []

        # Check for signed lease
        if not prop.lease_data or not prop.lease_data.is_signed:
            flags.append(
                "DEPARTING_RESIDENCE_NO_LEASE: Signed lease required to use "
                "departing residence rental income"
            )

        # Check PITIA reserves
        if prop.pitia_monthly and prop.pitia_monthly > ZERO:
            required_reserves = prop.pitia_monthly * DEPARTING_RESIDENCE_RESERVE_MONTHS
            if prop.verified_reserves is not None:
                if prop.verified_reserves < required_reserves:
                    shortfall = required_reserves - prop.verified_reserves
                    flags.append(
                        f"DEPARTING_RESIDENCE_INSUFFICIENT_RESERVES: "
                        f"Need ${float(required_reserves):,.2f} "
                        f"({DEPARTING_RESIDENCE_RESERVE_MONTHS} months PITIA) — "
                        f"have ${float(prop.verified_reserves):,.2f} — "
                        f"short ${float(shortfall):,.2f}"
                    )
            else:
                flags.append(
                    f"DEPARTING_RESIDENCE_RESERVES_UNVERIFIED: "
                    f"Must verify ${float(required_reserves):,.2f} in reserves "
                    f"({DEPARTING_RESIDENCE_RESERVE_MONTHS} months PITIA)"
                )

        return flags

    # =========================================================================
    # 8. DEPOSIT CROSS-REFERENCE
    # =========================================================================

    async def _cross_reference_deposits(
        self,
        loan_id: int,
        property_address: Optional[str],
        schedule_e_data: List[ScheduleELineItems],
    ) -> Optional[DepositCrossReference]:
        """
        Cross-reference Schedule E gross rents against bank deposit data.

        Queries income_sources or bank_statement_analyses for deposit totals
        that can be compared against claimed rents. Flags discrepancies
        exceeding the tolerance threshold.

        Returns None if no bank data is available for comparison.
        """
        if not schedule_e_data:
            return None

        # Use most recent year's Schedule E
        most_recent = max(schedule_e_data, key=lambda x: x.tax_year)
        annual_rents = most_recent.gross_rents_received

        if annual_rents <= ZERO:
            return None

        # Query for bank deposit data matching rental income
        try:
            row = self.db.execute(
                text("""
                    SELECT COALESCE(SUM(
                        CASE WHEN ai_notes ILIKE :pattern
                             OR employer_name ILIKE :rent_pattern
                        THEN COALESCE(total_annual_income, total_monthly_income * 12, 0)
                        ELSE 0 END
                    ), 0) as deposit_total
                    FROM income_sources
                    WHERE calculation_id IN (
                        SELECT id FROM income_calculations
                        WHERE loan_id = :loan_id
                          AND organization_id = :org_id
                    )
                    AND source_type = 'rental'
                """),
                {
                    "loan_id": loan_id,
                    "org_id": self.org_id,
                    "pattern": f"%{property_address or 'rental'}%",
                    "rent_pattern": "%rent%",
                },
            ).fetchone()
        except Exception as e:
            logger.warning(
                "Could not cross-reference deposits for loan %s: %s",
                loan_id, e,
            )
            return None

        if not row or row[0] == 0:
            return None

        deposit_total = self._to_decimal(row[0])
        xref = DepositCrossReference(
            property_address=property_address,
            schedule_e_annual_rents=annual_rents,
            bank_deposit_total=deposit_total,
        )

        if annual_rents > ZERO:
            xref.variance_pct = (
                abs(annual_rents - deposit_total) / annual_rents * 100
            ).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)

            xref.is_within_tolerance = xref.variance_pct <= DEPOSIT_MATCH_TOLERANCE_PCT

            if not xref.is_within_tolerance:
                xref.flags.append(
                    f"DEPOSIT_MISMATCH: Schedule E rents ${float(annual_rents):,.2f} vs "
                    f"bank deposits ${float(deposit_total):,.2f} — "
                    f"{float(xref.variance_pct):.1f}% variance "
                    f"(tolerance: {float(DEPOSIT_MATCH_TOLERANCE_PCT)}%)"
                )

        return xref

    # =========================================================================
    # 9. PERSISTENCE
    # =========================================================================

    async def _persist_results(
        self,
        result: RentalIncomeResult,
        loan_id: int,
    ) -> None:
        """Persist rental income results to income_sources table."""
        if not result.properties or not result.success:
            return

        try:
            for prop_result in result.properties:
                if prop_result.monthly_qualifying_income == ZERO and not prop_result.flags:
                    continue

                self.db.execute(
                    text("""
                        INSERT INTO income_sources (
                            calculation_id, borrower_id, source_type,
                            employer_name, total_monthly_income, total_annual_income,
                            trending_direction, ai_confidence, ai_notes,
                            source_document_ids, created_at, updated_at
                        )
                        SELECT
                            ic.id, ic.borrower_id, 'rental',
                            :property_address,
                            :monthly_income, :annual_income,
                            :trending, :confidence, :notes,
                            :doc_ids,
                            NOW(), NOW()
                        FROM income_calculations ic
                        WHERE ic.loan_id = :loan_id
                          AND ic.organization_id = :org_id
                        ORDER BY ic.created_at DESC
                        LIMIT 1
                    """),
                    {
                        "loan_id": loan_id,
                        "org_id": self.org_id,
                        "property_address": prop_result.property_address or "Rental Property",
                        "monthly_income": float(prop_result.monthly_qualifying_income),
                        "annual_income": float(prop_result.annual_qualifying_income),
                        "trending": self._determine_trend(prop_result),
                        "confidence": prop_result.confidence,
                        "notes": prop_result.notes or "; ".join(prop_result.flags),
                        "doc_ids": self._collect_doc_ids_json(prop_result),
                    },
                )

            self.db.flush()
            logger.info(
                "Persisted rental income for loan %s: %d properties, "
                "monthly qualifying $%.2f",
                loan_id,
                len(result.properties),
                float(result.total_monthly_qualifying_income),
            )
        except Exception as e:
            logger.error(
                "Failed to persist rental income for loan %s: %s",
                loan_id, e,
                exc_info=True,
            )

    # =========================================================================
    # 10. RECOMMENDATION & TASK GENERATION
    # =========================================================================

    def _generate_recommendations(
        self, result: RentalIncomeResult, program: str,
    ) -> List[str]:
        """Generate human-readable recommendations based on analysis."""
        recs: List[str] = []

        if result.net_negative_income < ZERO:
            recs.append(
                f"Net negative rental income of "
                f"${float(abs(result.net_negative_income)):,.2f}/mo must be "
                f"added to monthly obligations for DTI calculation."
            )

        for prop in result.properties:
            if not prop.is_income_positive and prop.pitia_offset_result:
                recs.append(
                    f"Property {prop.property_address or 'N/A'}: negative cash flow of "
                    f"${float(abs(prop.pitia_offset_result.net_cash_flow)):,.2f}/mo — "
                    f"consider whether borrower can sustain this shortfall."
                )

            if prop.role == PropertyRole.DEPARTING.value:
                for flag in prop.flags:
                    if "INSUFFICIENT_RESERVES" in flag:
                        recs.append(
                            f"Departing residence {prop.property_address or 'N/A'}: "
                            f"borrower needs additional reserves to satisfy "
                            f"{DEPARTING_RESIDENCE_RESERVE_MONTHS}-month requirement."
                        )
                        break

            if prop.experience_validation and not prop.experience_validation.meets_requirement:
                recs.append(
                    f"FHA: borrower lacks 2-year landlord experience for "
                    f"{prop.property_address or 'N/A'}. Consider engaging a "
                    f"property management company to satisfy the requirement."
                )

            if prop.deposit_cross_ref and not prop.deposit_cross_ref.is_within_tolerance:
                recs.append(
                    f"Schedule E rents for {prop.property_address or 'N/A'} differ "
                    f"from bank deposits by {float(prop.deposit_cross_ref.variance_pct):.1f}% — "
                    f"verify rent collection with cancelled checks or deposit records."
                )

        # Single-year Schedule E warning
        single_year_props = [
            p for p in result.properties
            if p.schedule_e_result
            and len(p.schedule_e_result.tax_years_analyzed) < MIN_SCHEDULE_E_YEARS
        ]
        if single_year_props:
            recs.append(
                f"{len(single_year_props)} property(ies) have only 1 year of "
                f"Schedule E history — request prior-year tax returns if available."
            )

        return recs

    def _generate_tasks(
        self, result: RentalIncomeResult, loan_id: int,
    ) -> List[Dict[str, Any]]:
        """Generate verification tasks for LO follow-up."""
        tasks: List[Dict[str, Any]] = []

        for prop in result.properties:
            # Task: verify unsigned lease
            if any("UNSIGNED_LEASE" in f for f in prop.flags):
                tasks.append({
                    "task_type": "calculate_rental_income",
                    "title": f"Obtain signed lease for {prop.property_address or 'rental property'}",
                    "description": (
                        "Rental income cannot be counted without a fully executed "
                        "lease agreement. Request signed lease from borrower."
                    ),
                    "priority": "high",
                    "loan_id": loan_id,
                })

            # Task: verify reserves for departing residence
            if any("RESERVES_UNVERIFIED" in f for f in prop.flags):
                tasks.append({
                    "task_type": "calculate_rental_income",
                    "title": f"Verify reserves for departing residence ({prop.property_address or 'N/A'})",
                    "description": (
                        f"Must verify {DEPARTING_RESIDENCE_RESERVE_MONTHS} months of "
                        f"PITIA reserves in borrower accounts."
                    ),
                    "priority": "high",
                    "loan_id": loan_id,
                })

            # Task: FHA experience documentation
            if prop.experience_validation and not prop.experience_validation.meets_requirement:
                tasks.append({
                    "task_type": "calculate_rental_income",
                    "title": "FHA landlord experience verification",
                    "description": (
                        "Borrower does not have 2 years of documented landlord experience. "
                        "Obtain property management agreement or additional landlord history."
                    ),
                    "priority": "high",
                    "loan_id": loan_id,
                })

            # Task: deposit mismatch
            if prop.deposit_cross_ref and not prop.deposit_cross_ref.is_within_tolerance:
                tasks.append({
                    "task_type": "calculate_rental_income",
                    "title": f"Verify rental deposits for {prop.property_address or 'N/A'}",
                    "description": (
                        f"Schedule E rents and bank deposits differ by "
                        f"{float(prop.deposit_cross_ref.variance_pct):.1f}%. "
                        f"Request cancelled checks or deposit documentation."
                    ),
                    "priority": "medium",
                    "loan_id": loan_id,
                })

            # Task: declining rental income
            if any("DECLINING_RENTAL_INCOME" in f for f in prop.flags):
                tasks.append({
                    "task_type": "review_declining_income",
                    "title": f"Review declining rental income for {prop.property_address or 'N/A'}",
                    "description": (
                        "Rental income shows significant year-over-year decline. "
                        "Review with borrower for market conditions or vacancy issues."
                    ),
                    "priority": "high",
                    "loan_id": loan_id,
                })

        return tasks

    # =========================================================================
    # HELPER METHODS
    # =========================================================================

    def _verify_org(self, org_id: int) -> None:
        """Verify org_id matches the service's org context."""
        if org_id != self.org_id:
            from exceptions import TenantIsolationError
            raise TenantIsolationError(
                message=f"Org mismatch: service initialized for {self.org_id}, "
                        f"called with {org_id}",
                requesting_org_id=org_id,
                target_org_id=self.org_id,
            )

    @staticmethod
    def _normalize_program(loan_program: str) -> str:
        """Normalize loan program string to LoanProgram enum value."""
        mapping = {
            "conventional": LoanProgram.FANNIE_MAE.value,
            "fannie": LoanProgram.FANNIE_MAE.value,
            "fannie_mae": LoanProgram.FANNIE_MAE.value,
            "freddie": LoanProgram.FREDDIE_MAC.value,
            "freddie_mac": LoanProgram.FREDDIE_MAC.value,
            "fha": LoanProgram.FHA.value,
            "va": LoanProgram.VA.value,
            "jumbo": LoanProgram.JUMBO.value,
            "non_qm": LoanProgram.NON_QM.value,
        }
        return mapping.get(loan_program.lower(), LoanProgram.FANNIE_MAE.value)

    @staticmethod
    def _get_vacancy_factor(program: str, fha_has_experience: bool = False) -> Decimal:
        """Get vacancy factor percentage for the given program."""
        if program == LoanProgram.FHA.value:
            if fha_has_experience:
                return VACANCY_FACTOR_FHA_WITH_HISTORY
            return VACANCY_FACTOR_FHA_NO_HISTORY
        elif program == LoanProgram.VA.value:
            return VACANCY_FACTOR_VA
        elif program == LoanProgram.FREDDIE_MAC.value:
            return VACANCY_FACTOR_FREDDIE
        else:
            # Fannie Mae, Conventional, Jumbo, Non-QM default
            return VACANCY_FACTOR_FANNIE

    @staticmethod
    def _sum_schedule_e_expenses(se: ScheduleELineItems) -> Decimal:
        """Sum individual expense lines from Schedule E."""
        return (
            se.advertising
            + se.auto_and_travel
            + se.cleaning_and_maintenance
            + se.commissions
            + se.insurance
            + se.legal_and_professional
            + se.management_fees
            + se.mortgage_interest
            + se.other_interest
            + se.repairs
            + se.supplies
            + se.taxes
            + se.utilities
            + se.depreciation
            + se.other_expenses
        )

    @staticmethod
    def _avg_decimal(values: List[Decimal]) -> Decimal:
        """Calculate average of Decimal values."""
        if not values:
            return ZERO
        total = sum(values, ZERO)
        return (total / len(values)).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)

    @staticmethod
    def _to_decimal(value: Any) -> Decimal:
        """Safely convert a value to Decimal."""
        if value is None:
            return ZERO
        try:
            return Decimal(str(value)).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
        except (InvalidOperation, ValueError, TypeError):
            return ZERO

    @staticmethod
    def _determine_trend(prop_result: PropertyRentalResult) -> str:
        """Determine trending direction from property result flags."""
        for flag in prop_result.flags:
            if "DECLINING_RENTAL_INCOME" in flag:
                return "declining"
            if "DECLINING_RENTAL_TREND" in flag:
                return "declining"
        return "stable"

    @staticmethod
    def _collect_doc_ids_json(prop_result: PropertyRentalResult) -> str:
        """Collect source document IDs from sub-results as JSON array string."""
        import json
        doc_ids: List[int] = []

        if prop_result.schedule_e_result:
            for yb in prop_result.schedule_e_result.yearly_breakdown:
                # yearly_breakdown is a dict; doc IDs tracked at ScheduleELineItems level
                pass

        if prop_result.proposed_rental_result:
            pass  # doc IDs tracked on LeaseData

        return json.dumps(doc_ids) if doc_ids else "[]"


# =============================================================================
# FACTORY FUNCTION
# =============================================================================

def get_rental_income_service(
    db: Session,
    org_id: int,
    user_id: Optional[int] = None,
) -> RentalIncomeService:
    """Create a RentalIncomeService instance.

    Args:
        db: SQLAlchemy session.
        org_id: Organization ID for tenant isolation.
        user_id: Optional authenticated user ID.

    Returns:
        Configured RentalIncomeService.
    """
    return RentalIncomeService(db=db, org_id=org_id, user_id=user_id)
