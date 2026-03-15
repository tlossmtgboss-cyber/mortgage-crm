"""
Guideline Eligibility Engine
Determines loan eligibility against Fannie Mae, Freddie Mac, FHA, and VA guidelines.
Key capabilities:
- Product eligibility matching
- LTV/CLTV limit verification
- Credit score minimums by program
- DTI limit validation
- Property type eligibility
- Occupancy requirements
- Maximum loan amounts
- Waiting period verification (BK, FC, SS)
"""

from dataclasses import dataclass, field
from datetime import datetime, date, timedelta
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple
import logging

logger = logging.getLogger(__name__)


class Agency(str, Enum):
    """Mortgage agency/investor."""
    FANNIE_MAE = "fnma"
    FREDDIE_MAC = "fhlmc"
    FHA = "fha"
    VA = "va"
    USDA = "usda"
    NON_QM = "non_qm"
    JUMBO = "jumbo"


class LoanPurpose(str, Enum):
    """Loan purpose types."""
    PURCHASE = "purchase"
    RATE_TERM_REFI = "rate_term"
    CASH_OUT_REFI = "cash_out"
    CONSTRUCTION = "construction"
    RENOVATION = "renovation"


class PropertyType(str, Enum):
    """Property types."""
    SINGLE_FAMILY = "sfr"
    CONDO = "condo"
    TOWNHOUSE = "townhouse"
    PUD = "pud"
    TWO_UNIT = "2_unit"
    THREE_UNIT = "3_unit"
    FOUR_UNIT = "4_unit"
    MANUFACTURED = "manufactured"
    CO_OP = "coop"


class OccupancyType(str, Enum):
    """Occupancy types."""
    PRIMARY = "primary"
    SECOND_HOME = "second_home"
    INVESTMENT = "investment"


class DocumentationType(str, Enum):
    """Income documentation types."""
    FULL_DOC = "full"
    BANK_STATEMENT = "bank_statement"
    ASSET_DEPLETION = "asset_depletion"
    DSCR = "dscr"
    NO_DOC = "no_doc"


@dataclass
class EligibilityResult:
    """Result of eligibility evaluation."""
    eligible: bool
    agency: Agency
    program_name: str
    confidence_score: float  # 0-100
    findings: List[Dict[str, Any]] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    ineligibility_reasons: List[str] = field(default_factory=list)
    max_ltv: Optional[float] = None
    max_cltv: Optional[float] = None
    max_dti: Optional[float] = None
    min_credit_score: Optional[int] = None
    max_loan_amount: Optional[Decimal] = None
    required_reserves_months: Optional[int] = None
    mi_required: bool = False
    restrictions: List[str] = field(default_factory=list)


@dataclass
class LoanScenario:
    """Input loan scenario for eligibility check."""
    loan_amount: Decimal
    property_value: Decimal
    loan_purpose: LoanPurpose
    property_type: PropertyType
    occupancy: OccupancyType
    credit_score: int
    dti_ratio: float
    ltv: float
    cltv: float
    property_state: str
    property_county: str
    is_first_time_buyer: bool = False
    has_subordinate_financing: bool = False
    num_units: int = 1
    borrower_citizenship: str = "us_citizen"  # us_citizen, permanent_resident, non_permanent_resident
    documentation_type: DocumentationType = DocumentationType.FULL_DOC
    months_reserves: int = 0

    # Derogatory events
    bankruptcy_date: Optional[date] = None
    bankruptcy_chapter: Optional[int] = None  # 7, 11, 12, 13
    foreclosure_date: Optional[date] = None
    short_sale_date: Optional[date] = None
    deed_in_lieu_date: Optional[date] = None

    # Property specifics
    is_rural: bool = False
    is_manufactured: bool = False
    condo_project_approval: Optional[str] = None

    # VA specifics
    is_veteran: bool = False
    va_entitlement_available: Optional[Decimal] = None
    va_funding_fee_exempt: bool = False


# 2026 Conforming Loan Limits (FHFA announcement, effective Jan 1 2026)
CONFORMING_LIMITS = {
    "standard": Decimal("832750"),
    "high_cost": Decimal("1249125"),
    "super_conforming": Decimal("1249125"),
    # High-cost areas (subset for reference)
    "high_cost_areas": {
        "CA": ["Los Angeles", "San Francisco", "Orange", "Santa Clara", "San Mateo", "Marin", "Alameda"],
        "NY": ["New York", "Kings", "Queens", "Bronx", "Richmond", "Nassau", "Suffolk", "Westchester"],
        "DC": ["District of Columbia"],
        "HI": ["*"],  # All Hawaii counties
        "AK": ["*"],  # All Alaska areas
    }
}


# 2026 FHA Loan Limits (HUD announcement, effective Jan 1 2026)
FHA_LIMITS = {
    "floor": Decimal("541287"),
    "ceiling": Decimal("1249125"),
}


class ConventionalEligibility:
    """Fannie Mae and Freddie Mac eligibility rules."""

    # LTV limits by occupancy, purpose, units, and property type
    LTV_LIMITS = {
        # Primary residence
        (OccupancyType.PRIMARY, LoanPurpose.PURCHASE, 1, PropertyType.SINGLE_FAMILY): {"ltv": 97, "cltv": 97},
        (OccupancyType.PRIMARY, LoanPurpose.PURCHASE, 1, PropertyType.CONDO): {"ltv": 97, "cltv": 97},
        (OccupancyType.PRIMARY, LoanPurpose.PURCHASE, 1, PropertyType.PUD): {"ltv": 97, "cltv": 97},
        (OccupancyType.PRIMARY, LoanPurpose.PURCHASE, 2, None): {"ltv": 85, "cltv": 85},
        (OccupancyType.PRIMARY, LoanPurpose.PURCHASE, 3, None): {"ltv": 75, "cltv": 75},
        (OccupancyType.PRIMARY, LoanPurpose.PURCHASE, 4, None): {"ltv": 75, "cltv": 75},
        (OccupancyType.PRIMARY, LoanPurpose.RATE_TERM_REFI, 1, None): {"ltv": 97, "cltv": 97},
        (OccupancyType.PRIMARY, LoanPurpose.CASH_OUT_REFI, 1, None): {"ltv": 80, "cltv": 80},
        (OccupancyType.PRIMARY, LoanPurpose.CASH_OUT_REFI, 2, None): {"ltv": 75, "cltv": 75},
        (OccupancyType.PRIMARY, LoanPurpose.CASH_OUT_REFI, 3, None): {"ltv": 75, "cltv": 75},
        (OccupancyType.PRIMARY, LoanPurpose.CASH_OUT_REFI, 4, None): {"ltv": 75, "cltv": 75},

        # Second home
        (OccupancyType.SECOND_HOME, LoanPurpose.PURCHASE, 1, None): {"ltv": 90, "cltv": 90},
        (OccupancyType.SECOND_HOME, LoanPurpose.RATE_TERM_REFI, 1, None): {"ltv": 90, "cltv": 90},
        (OccupancyType.SECOND_HOME, LoanPurpose.CASH_OUT_REFI, 1, None): {"ltv": 75, "cltv": 75},

        # Investment
        (OccupancyType.INVESTMENT, LoanPurpose.PURCHASE, 1, None): {"ltv": 85, "cltv": 85},
        (OccupancyType.INVESTMENT, LoanPurpose.PURCHASE, 2, None): {"ltv": 75, "cltv": 75},
        (OccupancyType.INVESTMENT, LoanPurpose.PURCHASE, 3, None): {"ltv": 75, "cltv": 75},
        (OccupancyType.INVESTMENT, LoanPurpose.PURCHASE, 4, None): {"ltv": 75, "cltv": 75},
        (OccupancyType.INVESTMENT, LoanPurpose.RATE_TERM_REFI, 1, None): {"ltv": 75, "cltv": 75},
        (OccupancyType.INVESTMENT, LoanPurpose.CASH_OUT_REFI, 1, None): {"ltv": 75, "cltv": 75},
    }

    # Credit score requirements
    MIN_CREDIT_SCORE = 620
    MIN_CREDIT_SCORE_HIGH_LTV = 660  # For LTV > 95%

    # DTI limits
    MAX_DTI_STANDARD = 45
    MAX_DTI_AUS_APPROVED = 50

    # Waiting periods (in months)
    WAITING_PERIODS = {
        "bankruptcy_ch7": 48,  # 4 years
        "bankruptcy_ch13": 24,  # 2 years from discharge, 4 from dismissal
        "foreclosure": 84,  # 7 years
        "short_sale": 48,  # 4 years
        "deed_in_lieu": 48,  # 4 years
    }

    # Reserve requirements (months PITI)
    RESERVE_REQUIREMENTS = {
        (OccupancyType.PRIMARY, 1): 0,
        (OccupancyType.PRIMARY, 2): 2,
        (OccupancyType.PRIMARY, 3): 6,
        (OccupancyType.PRIMARY, 4): 6,
        (OccupancyType.SECOND_HOME, 1): 2,
        (OccupancyType.INVESTMENT, 1): 6,
        (OccupancyType.INVESTMENT, 2): 6,
        (OccupancyType.INVESTMENT, 3): 6,
        (OccupancyType.INVESTMENT, 4): 6,
    }

    def check_eligibility(self, scenario: LoanScenario) -> EligibilityResult:
        """Check conventional loan eligibility."""
        findings = []
        warnings = []
        ineligible_reasons = []

        # Determine if high-cost area
        is_high_cost = self._is_high_cost_area(scenario.property_state, scenario.property_county)
        conforming_limit = CONFORMING_LIMITS["high_cost"] if is_high_cost else CONFORMING_LIMITS["standard"]

        # Check loan amount
        if scenario.loan_amount > conforming_limit:
            ineligible_reasons.append(f"Loan amount ${scenario.loan_amount:,.0f} exceeds conforming limit ${conforming_limit:,.0f}")

        # Check credit score
        min_score = self.MIN_CREDIT_SCORE
        if scenario.ltv > 95:
            min_score = self.MIN_CREDIT_SCORE_HIGH_LTV

        if scenario.credit_score < min_score:
            ineligible_reasons.append(f"Credit score {scenario.credit_score} below minimum {min_score}")

        # Check LTV/CLTV limits
        ltv_limits = self._get_ltv_limits(scenario)
        max_ltv = ltv_limits.get("ltv", 80)
        max_cltv = ltv_limits.get("cltv", 80)

        if scenario.ltv > max_ltv:
            ineligible_reasons.append(f"LTV {scenario.ltv:.1f}% exceeds maximum {max_ltv}%")

        if scenario.cltv > max_cltv:
            ineligible_reasons.append(f"CLTV {scenario.cltv:.1f}% exceeds maximum {max_cltv}%")

        # Check DTI
        max_dti = self.MAX_DTI_AUS_APPROVED
        if scenario.dti_ratio > max_dti:
            ineligible_reasons.append(f"DTI {scenario.dti_ratio:.1f}% exceeds maximum {max_dti}%")
        elif scenario.dti_ratio > self.MAX_DTI_STANDARD:
            warnings.append(f"DTI {scenario.dti_ratio:.1f}% exceeds standard limit, requires AUS approval")

        # Check property type eligibility
        if scenario.property_type == PropertyType.CO_OP:
            ineligible_reasons.append("Co-ops not eligible for conventional loans in most markets")

        if scenario.is_manufactured:
            if scenario.occupancy == OccupancyType.INVESTMENT:
                ineligible_reasons.append("Manufactured homes not eligible as investment property")
            elif scenario.ltv > 95:
                ineligible_reasons.append("Manufactured homes limited to 95% LTV")

        # Check waiting periods
        today = date.today()

        if scenario.bankruptcy_date:
            months_since = self._months_between(scenario.bankruptcy_date, today)
            wait_key = f"bankruptcy_ch{scenario.bankruptcy_chapter or 7}"
            required_months = self.WAITING_PERIODS.get(wait_key, 48)
            if months_since < required_months:
                remaining = required_months - months_since
                ineligible_reasons.append(f"Bankruptcy waiting period: {remaining} months remaining")

        if scenario.foreclosure_date:
            months_since = self._months_between(scenario.foreclosure_date, today)
            required = self.WAITING_PERIODS["foreclosure"]
            if months_since < required:
                remaining = required - months_since
                ineligible_reasons.append(f"Foreclosure waiting period: {remaining} months remaining")

        if scenario.short_sale_date:
            months_since = self._months_between(scenario.short_sale_date, today)
            required = self.WAITING_PERIODS["short_sale"]
            if months_since < required:
                remaining = required - months_since
                ineligible_reasons.append(f"Short sale waiting period: {remaining} months remaining")

        # Check reserves
        reserve_key = (scenario.occupancy, min(scenario.num_units, 4))
        required_reserves = self.RESERVE_REQUIREMENTS.get(reserve_key, 6)

        if scenario.months_reserves < required_reserves:
            warnings.append(f"Reserves {scenario.months_reserves} months below required {required_reserves} months")

        # Check citizenship
        if scenario.borrower_citizenship not in ["us_citizen", "permanent_resident"]:
            warnings.append("Non-permanent residents may have additional documentation requirements")

        # Determine MI requirement
        mi_required = scenario.ltv > 80

        # Calculate confidence
        eligible = len(ineligible_reasons) == 0
        confidence = 100 if eligible else max(0, 100 - len(ineligible_reasons) * 25)

        # Add positive findings
        if scenario.credit_score >= 740:
            findings.append({"type": "positive", "message": "Excellent credit score for best pricing"})
        if scenario.ltv <= 80:
            findings.append({"type": "positive", "message": "No mortgage insurance required"})
        if scenario.dti_ratio <= 36:
            findings.append({"type": "positive", "message": "Strong DTI ratio"})

        return EligibilityResult(
            eligible=eligible,
            agency=Agency.FANNIE_MAE,
            program_name="Conventional Conforming",
            confidence_score=confidence,
            findings=findings,
            warnings=warnings,
            ineligibility_reasons=ineligible_reasons,
            max_ltv=max_ltv,
            max_cltv=max_cltv,
            max_dti=max_dti,
            min_credit_score=min_score,
            max_loan_amount=conforming_limit,
            required_reserves_months=required_reserves,
            mi_required=mi_required,
        )

    def _get_ltv_limits(self, scenario: LoanScenario) -> Dict[str, int]:
        """Get LTV limits for scenario."""
        # Try exact match first
        key = (scenario.occupancy, scenario.loan_purpose, scenario.num_units, scenario.property_type)
        if key in self.LTV_LIMITS:
            return self.LTV_LIMITS[key]

        # Try without property type
        key = (scenario.occupancy, scenario.loan_purpose, scenario.num_units, None)
        if key in self.LTV_LIMITS:
            return self.LTV_LIMITS[key]

        # Default
        return {"ltv": 80, "cltv": 80}

    def _is_high_cost_area(self, state: str, county: str) -> bool:
        """Check if area is high-cost."""
        high_cost_counties = CONFORMING_LIMITS["high_cost_areas"].get(state.upper(), [])
        if "*" in high_cost_counties:
            return True
        return county in high_cost_counties

    def _months_between(self, start: date, end: date) -> int:
        """Calculate months between two dates."""
        return (end.year - start.year) * 12 + (end.month - start.month)


class FHAEligibility:
    """FHA loan eligibility rules."""

    # LTV limits
    LTV_LIMITS = {
        (LoanPurpose.PURCHASE, True): 96.5,  # With >= 580 credit
        (LoanPurpose.PURCHASE, False): 90.0,  # With 500-579 credit
        (LoanPurpose.RATE_TERM_REFI, True): 97.75,
        (LoanPurpose.CASH_OUT_REFI, True): 80.0,
    }

    # Credit score tiers
    MIN_CREDIT_STANDARD = 580
    MIN_CREDIT_LIMITED = 500

    # DTI limits
    MAX_DTI_FRONT = 46.99  # Housing ratio
    MAX_DTI_BACK = 56.99  # Total DTI with compensating factors
    MAX_DTI_STANDARD = 43.0

    # Waiting periods
    WAITING_PERIODS = {
        "bankruptcy_ch7": 24,  # 2 years
        "bankruptcy_ch13": 12,  # 1 year into payment plan
        "foreclosure": 36,  # 3 years
        "short_sale": 36,  # 3 years
    }

    # Upfront MIP rates
    UFMIP_RATE = Decimal("1.75")  # 1.75% of loan amount

    # Annual MIP rates
    ANNUAL_MIP = {
        "high_ltv_long_term": 0.55,  # > 90% LTV, > 15 years
        "high_ltv_short_term": 0.50,  # > 90% LTV, <= 15 years
        "low_ltv_long_term": 0.50,  # <= 90% LTV, > 15 years
        "low_ltv_short_term": 0.45,  # <= 90% LTV, <= 15 years
    }

    def check_eligibility(self, scenario: LoanScenario) -> EligibilityResult:
        """Check FHA loan eligibility."""
        findings = []
        warnings = []
        ineligible_reasons = []

        # Get FHA limit for area
        fha_limit = self._get_fha_limit(scenario.property_state, scenario.property_county)

        # Check loan amount
        if scenario.loan_amount > fha_limit:
            ineligible_reasons.append(f"Loan amount ${scenario.loan_amount:,.0f} exceeds FHA limit ${fha_limit:,.0f}")

        # Check credit score
        has_standard_credit = scenario.credit_score >= self.MIN_CREDIT_STANDARD

        if scenario.credit_score < self.MIN_CREDIT_LIMITED:
            ineligible_reasons.append(f"Credit score {scenario.credit_score} below FHA minimum 500")
        elif scenario.credit_score < self.MIN_CREDIT_STANDARD:
            warnings.append(f"Credit score {scenario.credit_score} limits LTV to 90%")

        # Check LTV
        max_ltv = self.LTV_LIMITS.get((scenario.loan_purpose, has_standard_credit), 96.5)

        if scenario.ltv > max_ltv:
            ineligible_reasons.append(f"LTV {scenario.ltv:.1f}% exceeds maximum {max_ltv:.1f}%")

        # Check DTI
        max_dti = self.MAX_DTI_BACK
        if scenario.dti_ratio > max_dti:
            ineligible_reasons.append(f"DTI {scenario.dti_ratio:.1f}% exceeds FHA maximum {max_dti:.1f}%")
        elif scenario.dti_ratio > self.MAX_DTI_STANDARD:
            warnings.append(f"DTI {scenario.dti_ratio:.1f}% requires compensating factors")

        # Check occupancy - FHA requires owner occupancy
        if scenario.occupancy != OccupancyType.PRIMARY:
            ineligible_reasons.append("FHA requires owner-occupancy (primary residence)")

        # Check property type
        if scenario.property_type == PropertyType.CO_OP:
            warnings.append("Co-op must be FHA-approved")

        if scenario.is_manufactured:
            if scenario.num_units > 1:
                ineligible_reasons.append("FHA manufactured limited to single unit")

        # Check waiting periods
        today = date.today()

        if scenario.bankruptcy_date:
            months_since = self._months_between(scenario.bankruptcy_date, today)
            wait_key = f"bankruptcy_ch{scenario.bankruptcy_chapter or 7}"
            required = self.WAITING_PERIODS.get(wait_key, 24)
            if months_since < required:
                # Check for extenuating circumstances exception
                remaining = required - months_since
                if remaining <= 12:
                    warnings.append(f"Bankruptcy may qualify with extenuating circumstances documentation")
                else:
                    ineligible_reasons.append(f"Bankruptcy waiting period: {remaining} months remaining")

        if scenario.foreclosure_date:
            months_since = self._months_between(scenario.foreclosure_date, today)
            required = self.WAITING_PERIODS["foreclosure"]
            if months_since < required:
                remaining = required - months_since
                ineligible_reasons.append(f"Foreclosure waiting period: {remaining} months remaining")

        # Maximum financing for closing costs
        if scenario.ltv > 96.5:
            findings.append({"type": "info", "message": "Seller can contribute up to 6% for closing costs"})

        # MIP calculation
        ufmip = scenario.loan_amount * self.UFMIP_RATE / 100
        findings.append({"type": "cost", "message": f"Upfront MIP: ${ufmip:,.0f} (financeable)"})

        # Determine eligibility
        eligible = len(ineligible_reasons) == 0
        confidence = 100 if eligible else max(0, 100 - len(ineligible_reasons) * 25)

        return EligibilityResult(
            eligible=eligible,
            agency=Agency.FHA,
            program_name="FHA Insured",
            confidence_score=confidence,
            findings=findings,
            warnings=warnings,
            ineligibility_reasons=ineligible_reasons,
            max_ltv=max_ltv,
            max_cltv=max_ltv + 5,  # FHA allows subordinate financing
            max_dti=max_dti,
            min_credit_score=self.MIN_CREDIT_LIMITED,
            max_loan_amount=fha_limit,
            required_reserves_months=0,  # FHA doesn't require reserves for 1-2 units
            mi_required=True,  # Always required for FHA
        )

    def _get_fha_limit(self, state: str, county: str) -> Decimal:
        """Get FHA limit for area (simplified)."""
        # In production, would look up actual FHA limits by county
        # Using ceiling for high-cost areas
        high_cost_states = ["CA", "NY", "HI", "AK", "DC"]
        if state.upper() in high_cost_states:
            return FHA_LIMITS["ceiling"]
        return FHA_LIMITS["floor"]

    def _months_between(self, start: date, end: date) -> int:
        """Calculate months between two dates."""
        return (end.year - start.year) * 12 + (end.month - start.month)


class VAEligibility:
    """VA loan eligibility rules."""

    # VA has no LTV limit for purchase
    MAX_LTV_PURCHASE = 100.0
    MAX_LTV_CASHOUT = 90.0
    MAX_LTV_IRRRL = 100.0  # Interest Rate Reduction Refinance

    # Credit - VA has no minimum but lenders typically require
    TYPICAL_MIN_CREDIT = 580

    # DTI - VA uses residual income, not strict DTI
    SUGGESTED_MAX_DTI = 41.0  # Guideline, not hard limit

    # Funding fee rates (first use)
    FUNDING_FEE_PURCHASE = {
        "down_0": Decimal("2.15"),
        "down_5": Decimal("1.50"),
        "down_10": Decimal("1.25"),
    }

    # Waiting periods
    WAITING_PERIODS = {
        "bankruptcy_ch7": 24,
        "bankruptcy_ch13": 12,  # 1 year satisfactory payments
        "foreclosure": 24,  # 2 years
    }

    # Residual income requirements by region and family size
    RESIDUAL_INCOME = {
        "northeast": {1: 450, 2: 755, 3: 909, 4: 1025, 5: 1062},
        "midwest": {1: 441, 2: 738, 3: 889, 4: 1003, 5: 1039},
        "south": {1: 441, 2: 738, 3: 889, 4: 1003, 5: 1039},
        "west": {1: 491, 2: 823, 3: 990, 4: 1117, 5: 1158},
    }

    def check_eligibility(self, scenario: LoanScenario) -> EligibilityResult:
        """Check VA loan eligibility."""
        findings = []
        warnings = []
        ineligible_reasons = []

        # Check veteran status
        if not scenario.is_veteran:
            ineligible_reasons.append("VA loans require veteran/military service eligibility")

        # Check occupancy - VA requires owner occupancy
        if scenario.occupancy != OccupancyType.PRIMARY:
            ineligible_reasons.append("VA requires owner-occupancy (primary residence)")

        # Check property type
        if scenario.property_type == PropertyType.CO_OP:
            ineligible_reasons.append("Co-ops not eligible for VA financing")

        if scenario.num_units > 4:
            ineligible_reasons.append("VA limited to 4 units maximum")

        # No loan limit for full entitlement veterans (2020 and later)
        max_loan = None  # No limit with full entitlement

        if scenario.va_entitlement_available is not None:
            # If using partial entitlement, calculate limit
            if scenario.va_entitlement_available < scenario.loan_amount * Decimal("0.25"):
                warnings.append("Partial entitlement may require down payment")

        # LTV limits
        if scenario.loan_purpose == LoanPurpose.CASH_OUT_REFI:
            max_ltv = self.MAX_LTV_CASHOUT
            if scenario.ltv > max_ltv:
                ineligible_reasons.append(f"Cash-out refinance limited to {max_ltv}% LTV")
        else:
            max_ltv = self.MAX_LTV_PURCHASE

        # Credit score (lender overlay, not VA requirement)
        if scenario.credit_score < self.TYPICAL_MIN_CREDIT:
            warnings.append(f"Credit score {scenario.credit_score} below typical lender minimum {self.TYPICAL_MIN_CREDIT}")

        # DTI - VA uses residual income primarily
        if scenario.dti_ratio > self.SUGGESTED_MAX_DTI:
            warnings.append(f"DTI {scenario.dti_ratio:.1f}% above guideline; residual income will be evaluated")

        # Waiting periods
        today = date.today()

        if scenario.bankruptcy_date:
            months_since = self._months_between(scenario.bankruptcy_date, today)
            wait_key = f"bankruptcy_ch{scenario.bankruptcy_chapter or 7}"
            required = self.WAITING_PERIODS.get(wait_key, 24)
            if months_since < required:
                remaining = required - months_since
                ineligible_reasons.append(f"Bankruptcy waiting period: {remaining} months remaining")

        if scenario.foreclosure_date:
            months_since = self._months_between(scenario.foreclosure_date, today)
            required = self.WAITING_PERIODS["foreclosure"]
            if months_since < required:
                remaining = required - months_since
                ineligible_reasons.append(f"Foreclosure waiting period: {remaining} months remaining")

        # Funding fee
        if not scenario.va_funding_fee_exempt:
            down_payment_pct = (1 - scenario.ltv / 100) * 100
            if down_payment_pct >= 10:
                fee_rate = self.FUNDING_FEE_PURCHASE["down_10"]
            elif down_payment_pct >= 5:
                fee_rate = self.FUNDING_FEE_PURCHASE["down_5"]
            else:
                fee_rate = self.FUNDING_FEE_PURCHASE["down_0"]

            funding_fee = scenario.loan_amount * fee_rate / 100
            findings.append({"type": "cost", "message": f"VA Funding Fee: ${funding_fee:,.0f} ({fee_rate}%)"})
        else:
            findings.append({"type": "positive", "message": "Exempt from VA Funding Fee"})

        # VA benefits
        findings.append({"type": "positive", "message": "No mortgage insurance required"})
        findings.append({"type": "positive", "message": "100% financing available"})
        findings.append({"type": "positive", "message": "No down payment required"})

        # Determine eligibility
        eligible = len(ineligible_reasons) == 0
        confidence = 100 if eligible else max(0, 100 - len(ineligible_reasons) * 25)

        return EligibilityResult(
            eligible=eligible,
            agency=Agency.VA,
            program_name="VA Guaranteed",
            confidence_score=confidence,
            findings=findings,
            warnings=warnings,
            ineligibility_reasons=ineligible_reasons,
            max_ltv=max_ltv,
            max_cltv=max_ltv,
            max_dti=self.SUGGESTED_MAX_DTI,
            min_credit_score=self.TYPICAL_MIN_CREDIT,
            max_loan_amount=max_loan,
            required_reserves_months=0,
            mi_required=False,
        )

    def _months_between(self, start: date, end: date) -> int:
        """Calculate months between two dates."""
        return (end.year - start.year) * 12 + (end.month - start.month)


class EligibilityEngine:
    """
    Main eligibility engine that evaluates loan scenarios against all available programs.
    """

    def __init__(self):
        self.conventional = ConventionalEligibility()
        self.fha = FHAEligibility()
        self.va = VAEligibility()

    def evaluate_all_programs(self, scenario: LoanScenario) -> List[EligibilityResult]:
        """
        Evaluate scenario against all available loan programs.
        Returns sorted list with most eligible programs first.
        """
        results = []

        # Check conventional
        conv_result = self.conventional.check_eligibility(scenario)
        results.append(conv_result)

        # Check FHA (only if owner-occupied)
        if scenario.occupancy == OccupancyType.PRIMARY:
            fha_result = self.fha.check_eligibility(scenario)
            results.append(fha_result)

        # Check VA (only if veteran)
        if scenario.is_veteran:
            va_result = self.va.check_eligibility(scenario)
            results.append(va_result)

        # Sort by eligibility then confidence
        results.sort(key=lambda x: (-int(x.eligible), -x.confidence_score))

        return results

    def find_best_program(self, scenario: LoanScenario) -> Optional[EligibilityResult]:
        """Find the best eligible program for the scenario."""
        results = self.evaluate_all_programs(scenario)
        eligible = [r for r in results if r.eligible]
        return eligible[0] if eligible else None

    def get_program_comparison(self, scenario: LoanScenario) -> Dict[str, Any]:
        """
        Get detailed comparison of all programs.
        Useful for presenting options to borrowers.
        """
        results = self.evaluate_all_programs(scenario)

        comparison = {
            "scenario_summary": {
                "loan_amount": float(scenario.loan_amount),
                "property_value": float(scenario.property_value),
                "ltv": scenario.ltv,
                "credit_score": scenario.credit_score,
                "dti": scenario.dti_ratio,
            },
            "programs": [],
            "recommendation": None,
        }

        for result in results:
            program_info = {
                "agency": result.agency.value,
                "program_name": result.program_name,
                "eligible": result.eligible,
                "confidence": result.confidence_score,
                "max_ltv": result.max_ltv,
                "max_dti": result.max_dti,
                "min_credit_score": result.min_credit_score,
                "mi_required": result.mi_required,
                "issues": result.ineligibility_reasons,
                "warnings": result.warnings,
                "benefits": [f["message"] for f in result.findings if f.get("type") == "positive"],
            }
            comparison["programs"].append(program_info)

        # Set recommendation
        eligible_programs = [p for p in comparison["programs"] if p["eligible"]]
        if eligible_programs:
            # Prefer no MI, then lowest MI
            if any(not p["mi_required"] for p in eligible_programs):
                comparison["recommendation"] = next(
                    p["program_name"] for p in eligible_programs if not p["mi_required"]
                )
            else:
                comparison["recommendation"] = eligible_programs[0]["program_name"]

        return comparison

    def check_specific_program(
        self,
        scenario: LoanScenario,
        agency: Agency,
    ) -> EligibilityResult:
        """Check eligibility for a specific program."""
        if agency == Agency.FANNIE_MAE or agency == Agency.FREDDIE_MAC:
            return self.conventional.check_eligibility(scenario)
        elif agency == Agency.FHA:
            return self.fha.check_eligibility(scenario)
        elif agency == Agency.VA:
            return self.va.check_eligibility(scenario)
        else:
            return EligibilityResult(
                eligible=False,
                agency=agency,
                program_name=agency.value,
                confidence_score=0,
                ineligibility_reasons=[f"Program {agency.value} not yet implemented"],
            )


def check_loan_eligibility(
    loan_amount: float,
    property_value: float,
    credit_score: int,
    dti_ratio: float,
    loan_purpose: str = "purchase",
    property_type: str = "sfr",
    occupancy: str = "primary",
    property_state: str = "CA",
    property_county: str = "Los Angeles",
    is_veteran: bool = False,
    num_units: int = 1,
    **kwargs
) -> Dict[str, Any]:
    """
    Convenience function to check loan eligibility.

    Args:
        loan_amount: Requested loan amount
        property_value: Property value/purchase price
        credit_score: Borrower credit score
        dti_ratio: Debt-to-income ratio
        loan_purpose: purchase, rate_term, cash_out
        property_type: sfr, condo, townhouse, pud, etc.
        occupancy: primary, second_home, investment
        property_state: Two-letter state code
        property_county: County name
        is_veteran: Whether borrower is a veteran
        num_units: Number of units (1-4)
        **kwargs: Additional scenario parameters

    Returns:
        Dictionary with eligibility results for all programs
    """
    # Map string inputs to enums
    purpose_map = {
        "purchase": LoanPurpose.PURCHASE,
        "rate_term": LoanPurpose.RATE_TERM_REFI,
        "cash_out": LoanPurpose.CASH_OUT_REFI,
    }

    prop_map = {
        "sfr": PropertyType.SINGLE_FAMILY,
        "single_family": PropertyType.SINGLE_FAMILY,
        "condo": PropertyType.CONDO,
        "townhouse": PropertyType.TOWNHOUSE,
        "pud": PropertyType.PUD,
        "2_unit": PropertyType.TWO_UNIT,
        "3_unit": PropertyType.THREE_UNIT,
        "4_unit": PropertyType.FOUR_UNIT,
        "manufactured": PropertyType.MANUFACTURED,
    }

    occ_map = {
        "primary": OccupancyType.PRIMARY,
        "second_home": OccupancyType.SECOND_HOME,
        "investment": OccupancyType.INVESTMENT,
    }

    # Calculate LTV/CLTV
    ltv = (loan_amount / property_value) * 100
    cltv = kwargs.get("cltv", ltv)

    scenario = LoanScenario(
        loan_amount=Decimal(str(loan_amount)),
        property_value=Decimal(str(property_value)),
        loan_purpose=purpose_map.get(loan_purpose.lower(), LoanPurpose.PURCHASE),
        property_type=prop_map.get(property_type.lower(), PropertyType.SINGLE_FAMILY),
        occupancy=occ_map.get(occupancy.lower(), OccupancyType.PRIMARY),
        credit_score=credit_score,
        dti_ratio=dti_ratio,
        ltv=ltv,
        cltv=cltv,
        property_state=property_state,
        property_county=property_county,
        is_veteran=is_veteran,
        num_units=num_units,
        bankruptcy_date=kwargs.get("bankruptcy_date"),
        bankruptcy_chapter=kwargs.get("bankruptcy_chapter"),
        foreclosure_date=kwargs.get("foreclosure_date"),
        short_sale_date=kwargs.get("short_sale_date"),
        months_reserves=kwargs.get("months_reserves", 0),
        is_first_time_buyer=kwargs.get("is_first_time_buyer", False),
    )

    engine = EligibilityEngine()
    comparison = engine.get_program_comparison(scenario)

    return comparison
