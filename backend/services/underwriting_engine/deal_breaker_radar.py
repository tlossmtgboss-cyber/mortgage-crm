"""
Deal Breaker Radar Engine

Centralized hard-stop detection for mortgage underwriting.
Scans loan, credit, and income data against agency guidelines to identify
unresolvable disqualifiers BEFORE the full underwriting run.

Hard stops include:
- LTV exceeds product maximum
- Credit score below program minimum
- DTI exceeds maximum allowed
- BK discharge < seasoning requirement
- Foreclosure < seasoning requirement
- Active non-medical collections > threshold
- Self-employed income declining > 25% YoY
- Occupancy fraud indicators (non-owner-occupied claimed as primary)
- Fraud indicators (straw buyer, inflated value, undisclosed liability)

References:
- Fannie Mae Selling Guide B2/B3 (Eligibility / Credit)
- Freddie Mac Guide Chapters 4200-5500
- FHA 4000.1 II.A (Origination through Post-Closing)
- VA Pamphlet 26-7 (Lenders Handbook)
"""

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
from enum import Enum
from typing import Any, Dict, List, Optional
import logging

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

class HardStopType(str, Enum):
    """Classification of hard-stop reasons."""
    LTV_EXCEEDED = "ltv_exceeded"
    CREDIT_SCORE_BELOW_MIN = "credit_score_below_min"
    DTI_EXCEEDED = "dti_exceeded"
    BK_SEASONING = "bk_seasoning"
    FORECLOSURE_SEASONING = "foreclosure_seasoning"
    ACTIVE_COLLECTIONS = "active_collections"
    INCOME_DECLINING = "income_declining"
    OCCUPANCY_MISREPRESENTATION = "occupancy_misrepresentation"
    FRAUD_STRAW_BUYER = "fraud_straw_buyer"
    FRAUD_INFLATED_VALUE = "fraud_inflated_value"
    FRAUD_UNDISCLOSED_LIABILITY = "fraud_undisclosed_liability"
    PROPERTY_INELIGIBLE = "property_ineligible"
    EMPLOYMENT_GAP = "employment_gap"
    IDENTITY_MISMATCH = "identity_mismatch"
    OFAC_HIT = "ofac_hit"


class Severity(str, Enum):
    """Severity tier for hard stops."""
    CRITICAL = "critical"      # Absolute disqualifier, no override possible
    HIGH = "high"              # Disqualifier under standard guidelines
    ELEVATED = "elevated"      # May be resolvable with exception approval


@dataclass
class HardStop:
    """A single hard-stop finding from the radar scan."""
    type: HardStopType
    description: str
    severity: Severity
    guideline_reference: str
    is_waivable: bool
    details: Dict[str, Any] = field(default_factory=dict)
    detected_at: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.type.value,
            "description": self.description,
            "severity": self.severity.value,
            "guideline_reference": self.guideline_reference,
            "is_waivable": self.is_waivable,
            "details": self.details,
            "detected_at": self.detected_at.isoformat(),
        }


@dataclass
class RadarScanResult:
    """Aggregate result from a full radar sweep."""
    has_hard_stops: bool = False
    hard_stops: List[HardStop] = field(default_factory=list)
    scan_timestamp: datetime = field(default_factory=datetime.utcnow)
    loan_program: Optional[str] = None
    summary: str = ""

    @property
    def critical_count(self) -> int:
        return sum(1 for h in self.hard_stops if h.severity == Severity.CRITICAL)

    @property
    def is_dead_deal(self) -> bool:
        """True if any non-waivable CRITICAL stop exists."""
        return any(
            h.severity == Severity.CRITICAL and not h.is_waivable
            for h in self.hard_stops
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "has_hard_stops": self.has_hard_stops,
            "hard_stops": [h.to_dict() for h in self.hard_stops],
            "critical_count": self.critical_count,
            "is_dead_deal": self.is_dead_deal,
            "scan_timestamp": self.scan_timestamp.isoformat(),
            "loan_program": self.loan_program,
            "summary": self.summary,
        }


# ---------------------------------------------------------------------------
# Guideline thresholds by agency / program
# ---------------------------------------------------------------------------

_PROGRAM_LIMITS: Dict[str, Dict[str, Any]] = {
    "fnma_conforming": {
        "max_ltv": {"primary": Decimal("97"), "second_home": Decimal("90"), "investment": Decimal("85")},
        "min_credit_score": 620,
        "max_dti": Decimal("50"),
        "bk_ch7_seasoning_months": 48,
        "bk_ch13_seasoning_months": 24,
        "foreclosure_seasoning_months": 84,
        "max_non_medical_collections": 0,
        "agency_label": "Fannie Mae",
    },
    "fhlmc_conforming": {
        "max_ltv": {"primary": Decimal("97"), "second_home": Decimal("90"), "investment": Decimal("85")},
        "min_credit_score": 620,
        "max_dti": Decimal("50"),
        "bk_ch7_seasoning_months": 48,
        "bk_ch13_seasoning_months": 24,
        "foreclosure_seasoning_months": 84,
        "max_non_medical_collections": 0,
        "agency_label": "Freddie Mac",
    },
    "fha": {
        "max_ltv": {"primary": Decimal("96.5"), "second_home": Decimal("0"), "investment": Decimal("0")},
        "min_credit_score": 500,
        "min_credit_score_96_5_ltv": 580,
        "max_dti": Decimal("57"),
        "bk_ch7_seasoning_months": 24,
        "bk_ch13_seasoning_months": 12,
        "foreclosure_seasoning_months": 36,
        "max_non_medical_collections": 5,
        "agency_label": "FHA",
    },
    "va": {
        "max_ltv": {"primary": Decimal("100"), "second_home": Decimal("0"), "investment": Decimal("0")},
        "min_credit_score": 580,
        "max_dti": Decimal("60"),
        "bk_ch7_seasoning_months": 24,
        "bk_ch13_seasoning_months": 12,
        "foreclosure_seasoning_months": 24,
        "max_non_medical_collections": 0,
        "agency_label": "VA",
    },
    "usda": {
        "max_ltv": {"primary": Decimal("100"), "second_home": Decimal("0"), "investment": Decimal("0")},
        "min_credit_score": 640,
        "max_dti": Decimal("46"),
        "bk_ch7_seasoning_months": 36,
        "bk_ch13_seasoning_months": 12,
        "foreclosure_seasoning_months": 36,
        "max_non_medical_collections": 0,
        "agency_label": "USDA",
    },
}


# ---------------------------------------------------------------------------
# Radar engine
# ---------------------------------------------------------------------------

class DealBreakerRadar:
    """
    Centralized hard-stop detection engine.

    Runs a battery of checks against loan, credit, and income data to
    surface disqualifying conditions as early as possible.

    Usage::

        radar = DealBreakerRadar()
        hard_stops = await radar.scan(loan_data, credit_data, income_data)
        for stop in hard_stops:
            print(stop.type, stop.description)
    """

    def __init__(self, custom_limits: Optional[Dict[str, Dict]] = None):
        """
        Args:
            custom_limits: Override or extend _PROGRAM_LIMITS with org-specific
                           overlays (e.g. jumbo or Non-QM programs).
        """
        self.limits = dict(_PROGRAM_LIMITS)
        if custom_limits:
            self.limits.update(custom_limits)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def scan(
        self,
        loan_data: dict,
        credit_data: dict,
        income_data: dict,
    ) -> List[HardStop]:
        """
        Run all hard-stop checks and return findings.

        Args:
            loan_data: Dict with keys like loan_amount, property_value,
                       occupancy_type, loan_program, loan_purpose, etc.
            credit_data: Dict with credit_score, tradelines, derogatory_events,
                         active_collections, etc.
            income_data: Dict with qualifying_income, income_sources,
                         self_employment_history, etc.

        Returns:
            List of HardStop objects. Empty list == no hard stops found.
        """
        hard_stops: List[HardStop] = []
        program = loan_data.get("loan_program", "fnma_conforming")
        limits = self.limits.get(program)

        if not limits:
            logger.warning("No guideline limits for program %s — skipping programmatic checks", program)
            # Still run fraud checks which are program-agnostic
            limits = {}

        # Run all check families
        hard_stops.extend(self._check_ltv(loan_data, limits))
        hard_stops.extend(self._check_credit_score(loan_data, credit_data, limits))
        hard_stops.extend(self._check_dti(loan_data, credit_data, income_data, limits))
        hard_stops.extend(self._check_bk_seasoning(credit_data, limits))
        hard_stops.extend(self._check_foreclosure_seasoning(credit_data, limits))
        hard_stops.extend(self._check_collections(credit_data, limits))
        hard_stops.extend(self._check_income_declining(income_data))
        hard_stops.extend(self._check_occupancy(loan_data))
        hard_stops.extend(self._check_fraud_indicators(loan_data, credit_data, income_data))

        if hard_stops:
            logger.info(
                "DealBreakerRadar: %d hard stop(s) detected for program %s",
                len(hard_stops), program,
            )

        return hard_stops

    async def scan_all_programs(
        self,
        loan_data: dict,
        credit_data: dict,
        income_data: dict,
    ) -> Dict[str, RadarScanResult]:
        """
        Run the scan against every configured program and return results
        keyed by program name.  Useful for determining if *any* program
        would work for the borrower.
        """
        results: Dict[str, RadarScanResult] = {}
        for program_key in self.limits:
            modified_loan = {**loan_data, "loan_program": program_key}
            stops = await self.scan(modified_loan, credit_data, income_data)
            result = RadarScanResult(
                has_hard_stops=bool(stops),
                hard_stops=stops,
                loan_program=program_key,
                summary=self._build_summary(stops, program_key),
            )
            results[program_key] = result
        return results

    # ------------------------------------------------------------------
    # Individual check families
    # ------------------------------------------------------------------

    def _check_ltv(self, loan_data: dict, limits: dict) -> List[HardStop]:
        """LTV exceeds product maximum."""
        stops: List[HardStop] = []
        max_ltv_map = limits.get("max_ltv")
        if not max_ltv_map:
            return stops

        loan_amount = Decimal(str(loan_data.get("loan_amount", 0)))
        property_value = Decimal(str(loan_data.get("property_value", 0)))
        if property_value <= 0:
            return stops

        ltv = (loan_amount / property_value * 100).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        occupancy = loan_data.get("occupancy_type", "primary")
        max_ltv = max_ltv_map.get(occupancy, Decimal("0"))

        if max_ltv <= 0:
            # Program doesn't allow this occupancy at all
            stops.append(HardStop(
                type=HardStopType.LTV_EXCEEDED,
                description=f"{limits.get('agency_label', 'Program')} does not allow {occupancy} occupancy.",
                severity=Severity.CRITICAL,
                guideline_reference=f"{limits.get('agency_label', '')} occupancy eligibility",
                is_waivable=False,
                details={"occupancy": occupancy, "program": limits.get("agency_label")},
            ))
        elif ltv > max_ltv:
            stops.append(HardStop(
                type=HardStopType.LTV_EXCEEDED,
                description=(
                    f"LTV {ltv}% exceeds {limits.get('agency_label', 'program')} "
                    f"maximum of {max_ltv}% for {occupancy} occupancy."
                ),
                severity=Severity.CRITICAL,
                guideline_reference=f"{limits.get('agency_label', '')} Selling Guide — LTV Limits",
                is_waivable=False,
                details={"ltv": str(ltv), "max_ltv": str(max_ltv), "occupancy": occupancy},
            ))
        return stops

    def _check_credit_score(self, loan_data: dict, credit_data: dict, limits: dict) -> List[HardStop]:
        """Credit score below program minimum."""
        stops: List[HardStop] = []
        min_score = limits.get("min_credit_score")
        if min_score is None:
            return stops

        score = credit_data.get("credit_score")
        if score is None:
            return stops

        score = int(score)

        if score < min_score:
            stops.append(HardStop(
                type=HardStopType.CREDIT_SCORE_BELOW_MIN,
                description=(
                    f"Credit score {score} is below the {limits.get('agency_label', 'program')} "
                    f"minimum of {min_score}."
                ),
                severity=Severity.CRITICAL,
                guideline_reference=f"{limits.get('agency_label', '')} — Minimum Credit Score Requirements",
                is_waivable=False,
                details={"credit_score": score, "minimum_required": min_score},
            ))
            return stops

        # FHA special: score 500-579 requires max 90% LTV
        min_score_high_ltv = limits.get("min_credit_score_96_5_ltv")
        if min_score_high_ltv and score < min_score_high_ltv:
            loan_amount = Decimal(str(loan_data.get("loan_amount", 0)))
            property_value = Decimal(str(loan_data.get("property_value", 1)))
            ltv = (loan_amount / property_value * 100).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            if ltv > Decimal("90"):
                stops.append(HardStop(
                    type=HardStopType.CREDIT_SCORE_BELOW_MIN,
                    description=(
                        f"FHA: Credit score {score} requires max 90% LTV. "
                        f"Current LTV is {ltv}%."
                    ),
                    severity=Severity.CRITICAL,
                    guideline_reference="FHA 4000.1 II.A.5.a — Minimum Decision Credit Score",
                    is_waivable=False,
                    details={"credit_score": score, "ltv": str(ltv), "max_ltv_for_score": "90"},
                ))

        return stops

    def _check_dti(
        self,
        loan_data: dict,
        credit_data: dict,
        income_data: dict,
        limits: dict,
    ) -> List[HardStop]:
        """DTI exceeds program maximum."""
        stops: List[HardStop] = []
        max_dti = limits.get("max_dti")
        if max_dti is None:
            return stops

        total_monthly_debt = Decimal(str(credit_data.get("total_monthly_debt", 0)))
        proposed_payment = Decimal(str(loan_data.get("proposed_monthly_payment", 0)))
        qualifying_income = Decimal(str(income_data.get("qualifying_monthly_income", 0)))

        if qualifying_income <= 0:
            return stops

        total_obligations = total_monthly_debt + proposed_payment
        dti = (total_obligations / qualifying_income * 100).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )

        if dti > max_dti:
            stops.append(HardStop(
                type=HardStopType.DTI_EXCEEDED,
                description=(
                    f"Back-end DTI {dti}% exceeds {limits.get('agency_label', 'program')} "
                    f"maximum of {max_dti}%."
                ),
                severity=Severity.HIGH,
                guideline_reference=f"{limits.get('agency_label', '')} — DTI Limits",
                is_waivable=True,  # Some agencies allow exceptions with compensating factors
                details={
                    "dti": str(dti),
                    "max_dti": str(max_dti),
                    "total_monthly_debt": str(total_monthly_debt),
                    "proposed_payment": str(proposed_payment),
                    "qualifying_income": str(qualifying_income),
                },
            ))
        return stops

    def _check_bk_seasoning(self, credit_data: dict, limits: dict) -> List[HardStop]:
        """Bankruptcy discharge date < seasoning requirement."""
        stops: List[HardStop] = []
        derogatory_events = credit_data.get("derogatory_events", [])

        for event in derogatory_events:
            event_type = event.get("event_type", "")
            discharge_date_str = event.get("discharge_date")
            if not discharge_date_str:
                continue

            if "chapter_7" in event_type.lower() or "ch7" in event_type.lower():
                required_months = limits.get("bk_ch7_seasoning_months")
                label = "Chapter 7 Bankruptcy"
            elif "chapter_13" in event_type.lower() or "ch13" in event_type.lower():
                required_months = limits.get("bk_ch13_seasoning_months")
                label = "Chapter 13 Bankruptcy"
            else:
                continue

            if required_months is None:
                continue

            discharge_date = self._parse_date(discharge_date_str)
            if not discharge_date:
                continue

            months_elapsed = self._months_between(discharge_date, date.today())

            if months_elapsed < required_months:
                stops.append(HardStop(
                    type=HardStopType.BK_SEASONING,
                    description=(
                        f"{label} discharge {months_elapsed} months ago — "
                        f"{limits.get('agency_label', 'program')} requires {required_months} months."
                    ),
                    severity=Severity.CRITICAL,
                    guideline_reference=(
                        f"{limits.get('agency_label', '')} — Bankruptcy Waiting Period"
                    ),
                    is_waivable=False,
                    details={
                        "event_type": label,
                        "discharge_date": discharge_date_str,
                        "months_elapsed": months_elapsed,
                        "months_required": required_months,
                    },
                ))
        return stops

    def _check_foreclosure_seasoning(self, credit_data: dict, limits: dict) -> List[HardStop]:
        """Foreclosure / DIL / short sale < seasoning requirement."""
        stops: List[HardStop] = []
        required_months = limits.get("foreclosure_seasoning_months")
        if required_months is None:
            return stops

        derogatory_events = credit_data.get("derogatory_events", [])
        fc_types = {"foreclosure", "short_sale", "deed_in_lieu"}

        for event in derogatory_events:
            event_type = event.get("event_type", "").lower()
            if event_type not in fc_types:
                continue

            event_date_str = event.get("event_date") or event.get("discharge_date")
            if not event_date_str:
                continue

            event_date = self._parse_date(event_date_str)
            if not event_date:
                continue

            months_elapsed = self._months_between(event_date, date.today())
            if months_elapsed < required_months:
                label = event_type.replace("_", " ").title()
                stops.append(HardStop(
                    type=HardStopType.FORECLOSURE_SEASONING,
                    description=(
                        f"{label} was {months_elapsed} months ago — "
                        f"{limits.get('agency_label', 'program')} requires {required_months} months."
                    ),
                    severity=Severity.CRITICAL,
                    guideline_reference=(
                        f"{limits.get('agency_label', '')} — Foreclosure / DIL / SS Waiting Period"
                    ),
                    is_waivable=False,
                    details={
                        "event_type": label,
                        "event_date": event_date_str,
                        "months_elapsed": months_elapsed,
                        "months_required": required_months,
                    },
                ))
        return stops

    def _check_collections(self, credit_data: dict, limits: dict) -> List[HardStop]:
        """Active non-medical collections above threshold."""
        stops: List[HardStop] = []
        max_allowed = limits.get("max_non_medical_collections")
        if max_allowed is None:
            return stops

        collections = credit_data.get("active_collections", [])
        non_medical = [
            c for c in collections
            if not c.get("is_medical", False)
        ]

        if len(non_medical) > max_allowed:
            total_balance = sum(
                Decimal(str(c.get("balance", 0))) for c in non_medical
            )
            stops.append(HardStop(
                type=HardStopType.ACTIVE_COLLECTIONS,
                description=(
                    f"{len(non_medical)} active non-medical collection(s) "
                    f"(balance ${total_balance:,.2f}) — "
                    f"maximum allowed is {max_allowed}."
                ),
                severity=Severity.HIGH,
                guideline_reference=(
                    f"{limits.get('agency_label', '')} — Collection Account Requirements"
                ),
                is_waivable=True,  # May be payable at closing
                details={
                    "non_medical_count": len(non_medical),
                    "max_allowed": max_allowed,
                    "total_balance": str(total_balance),
                    "accounts": [
                        {"creditor": c.get("creditor", ""), "balance": str(c.get("balance", 0))}
                        for c in non_medical
                    ],
                },
            ))
        return stops

    def _check_income_declining(self, income_data: dict) -> List[HardStop]:
        """Self-employed income declining > 25% year-over-year."""
        stops: List[HardStop] = []
        se_history = income_data.get("self_employment_history", [])
        if not se_history or len(se_history) < 2:
            return stops

        # Expect list sorted most-recent first: [{year, net_income}, ...]
        sorted_history = sorted(se_history, key=lambda x: x.get("year", 0), reverse=True)
        current = Decimal(str(sorted_history[0].get("net_income", 0)))
        prior = Decimal(str(sorted_history[1].get("net_income", 0)))

        if prior <= 0:
            return stops

        decline_pct = ((prior - current) / prior * 100).quantize(
            Decimal("0.1"), rounding=ROUND_HALF_UP
        )

        if decline_pct > Decimal("25"):
            stops.append(HardStop(
                type=HardStopType.INCOME_DECLINING,
                description=(
                    f"Self-employment income declined {decline_pct}% YoY "
                    f"(${prior:,.0f} → ${current:,.0f}). Exceeds 25% threshold."
                ),
                severity=Severity.HIGH,
                guideline_reference=(
                    "Fannie Mae B3-3.2, Freddie Mac 5304.1 — "
                    "Self-Employment Income Trending Analysis"
                ),
                is_waivable=True,  # Underwriter discretion with compensating factors
                details={
                    "current_year_income": str(current),
                    "prior_year_income": str(prior),
                    "decline_percent": str(decline_pct),
                    "current_year": sorted_history[0].get("year"),
                    "prior_year": sorted_history[1].get("year"),
                },
            ))
        return stops

    def _check_occupancy(self, loan_data: dict) -> List[HardStop]:
        """Non-owner-occupied claimed as primary residence (fraud indicator)."""
        stops: List[HardStop] = []
        occupancy_flags = loan_data.get("occupancy_flags", {})
        if not occupancy_flags:
            return stops

        red_flags: List[str] = []

        # Distance from current employer
        commute_miles = occupancy_flags.get("commute_distance_miles")
        if commute_miles is not None and commute_miles > 100:
            red_flags.append(f"Commute distance {commute_miles} miles from employer")

        # Borrower already owns primary in different area
        if occupancy_flags.get("owns_other_primary"):
            red_flags.append("Borrower already owns another primary residence")

        # Mailing address differs from subject property
        if occupancy_flags.get("mailing_differs_from_subject"):
            red_flags.append("Mailing address differs from subject property")

        # Property is in vacation/resort area with no local employment
        if occupancy_flags.get("resort_area") and not occupancy_flags.get("local_employment"):
            red_flags.append("Property in resort area with no local employment")

        if red_flags:
            stops.append(HardStop(
                type=HardStopType.OCCUPANCY_MISREPRESENTATION,
                description=(
                    f"Possible occupancy misrepresentation: {'; '.join(red_flags)}"
                ),
                severity=Severity.ELEVATED,
                guideline_reference="FNMA B7-1, FHA 4000.1 II.A.1.a — Occupancy Verification",
                is_waivable=True,  # Borrower may provide explanation
                details={"red_flags": red_flags, "occupancy_flags": occupancy_flags},
            ))
        return stops

    def _check_fraud_indicators(
        self,
        loan_data: dict,
        credit_data: dict,
        income_data: dict,
    ) -> List[HardStop]:
        """Detect straw buyer, inflated value, undisclosed liability patterns."""
        stops: List[HardStop] = []

        # --- Straw buyer indicators ---
        straw_flags: List[str] = []
        if loan_data.get("non_arm_length_transaction") and loan_data.get("first_time_buyer"):
            straw_flags.append("Non-arm's-length transaction with first-time buyer")
        if loan_data.get("power_of_attorney") and loan_data.get("occupancy_type") == "investment":
            straw_flags.append("POA used on investment property purchase")
        if loan_data.get("large_earnest_money_gift"):
            straw_flags.append("Earnest money from gift on non-arm's-length transaction")

        if straw_flags:
            stops.append(HardStop(
                type=HardStopType.FRAUD_STRAW_BUYER,
                description=f"Straw buyer indicators: {'; '.join(straw_flags)}",
                severity=Severity.CRITICAL,
                guideline_reference="FNMA B7-1, SAR Filing Guidance — Straw Buyer Schemes",
                is_waivable=False,
                details={"indicators": straw_flags},
            ))

        # --- Inflated value indicators ---
        value_flags: List[str] = []
        appraisal_value = Decimal(str(loan_data.get("appraised_value", 0)))
        purchase_price = Decimal(str(loan_data.get("purchase_price", 0)))
        if appraisal_value > 0 and purchase_price > 0:
            spread = ((appraisal_value - purchase_price) / purchase_price * 100).quantize(
                Decimal("0.1"), rounding=ROUND_HALF_UP
            )
            if spread > Decimal("15"):
                value_flags.append(
                    f"Appraisal exceeds purchase price by {spread}%"
                )
        if loan_data.get("multiple_appraisals_ordered"):
            value_flags.append("Multiple appraisals ordered (possible value shopping)")
        if loan_data.get("rapid_appreciation"):
            value_flags.append("Property shows rapid appreciation inconsistent with market")

        if value_flags:
            stops.append(HardStop(
                type=HardStopType.FRAUD_INFLATED_VALUE,
                description=f"Value inflation indicators: {'; '.join(value_flags)}",
                severity=Severity.ELEVATED,
                guideline_reference="FNMA B4-1.3, Appraiser Independence Requirements",
                is_waivable=True,
                details={"indicators": value_flags},
            ))

        # --- Undisclosed liability indicators ---
        liability_flags: List[str] = []
        credit_inquiries_90d = credit_data.get("recent_inquiries_90_days", 0)
        if credit_inquiries_90d > 3:
            liability_flags.append(
                f"{credit_inquiries_90d} credit inquiries in last 90 days"
            )
        if credit_data.get("new_accounts_since_application"):
            new_count = len(credit_data["new_accounts_since_application"])
            if new_count > 0:
                liability_flags.append(
                    f"{new_count} new credit account(s) opened since application"
                )
        if income_data.get("undisclosed_debts_detected"):
            liability_flags.append("Bank statement analysis found undisclosed debts")

        if liability_flags:
            stops.append(HardStop(
                type=HardStopType.FRAUD_UNDISCLOSED_LIABILITY,
                description=f"Undisclosed liability indicators: {'; '.join(liability_flags)}",
                severity=Severity.HIGH,
                guideline_reference=(
                    "FNMA B3-6, FHA 4000.1 II.A.4 — Undisclosed Liabilities"
                ),
                is_waivable=True,
                details={"indicators": liability_flags},
            ))

        return stops

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_date(date_str: str) -> Optional[date]:
        """Parse ISO-format or common date strings."""
        for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%Y-%m-%dT%H:%M:%S"):
            try:
                return datetime.strptime(date_str, fmt).date()
            except (ValueError, TypeError):
                continue
        return None

    @staticmethod
    def _months_between(start: date, end: date) -> int:
        """Calculate approximate months between two dates."""
        return (end.year - start.year) * 12 + (end.month - start.month)

    @staticmethod
    def _build_summary(stops: List[HardStop], program: str) -> str:
        if not stops:
            return f"No hard stops detected for {program}."
        critical = sum(1 for s in stops if s.severity == Severity.CRITICAL)
        high = sum(1 for s in stops if s.severity == Severity.HIGH)
        elevated = sum(1 for s in stops if s.severity == Severity.ELEVATED)
        parts = []
        if critical:
            parts.append(f"{critical} critical")
        if high:
            parts.append(f"{high} high")
        if elevated:
            parts.append(f"{elevated} elevated")
        return f"{program}: {', '.join(parts)} hard stop(s) found."
