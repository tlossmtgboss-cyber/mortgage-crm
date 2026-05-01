"""
Underwriter Copilot Service

LO-facing agent that answers "Will my borrower qualify for this scenario?"
with cited guideline excerpts and a confidence score.

Wraps the existing GuidelineRAGService and EligibilityEngine into a unified
interface for the AI agent system.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Optional
import logging

from .eligibility_engine import (
    Agency, LoanPurpose, PropertyType, OccupancyType, DocumentationType,
    EligibilityResult,
)
from .guideline_rag_service import GuidelineRAGService, GuidelineResult

logger = logging.getLogger(__name__)


class ScenarioConfidence(str, Enum):
    HIGH = "high"
    MODERATE = "moderate"
    LOW = "low"
    INELIGIBLE = "ineligible"


@dataclass
class BorrowerScenario:
    credit_score: int
    annual_income: Decimal
    monthly_debts: Decimal
    loan_amount: Decimal
    property_value: Decimal
    property_type: str = "sfr"
    occupancy: str = "primary"
    loan_purpose: str = "purchase"
    documentation_type: str = "full"
    down_payment: Optional[Decimal] = None
    is_first_time_buyer: bool = False
    is_veteran: bool = False
    months_reserves: int = 0
    bankruptcy_date: Optional[datetime] = None
    foreclosure_date: Optional[datetime] = None
    self_employed: bool = False
    years_self_employed: int = 0
    citizenship: str = "us_citizen"


@dataclass
class GuidelineCitation:
    agency: str
    section: str
    title: str
    excerpt: str
    relevance: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "agency": self.agency,
            "section": self.section,
            "title": self.title,
            "excerpt": self.excerpt[:500],
            "relevance": round(self.relevance, 3),
        }


@dataclass
class CopilotAnalysis:
    question: str
    confidence: ScenarioConfidence
    confidence_score: float
    summary: str
    eligible_programs: List[Dict[str, Any]]
    ineligible_programs: List[Dict[str, Any]]
    risk_factors: List[str]
    mitigating_factors: List[str]
    citations: List[GuidelineCitation]
    recommendations: List[str]
    analyzed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "question": self.question,
            "confidence": self.confidence.value,
            "confidence_score": round(self.confidence_score, 1),
            "summary": self.summary,
            "eligible_programs": self.eligible_programs,
            "ineligible_programs": self.ineligible_programs,
            "risk_factors": self.risk_factors,
            "mitigating_factors": self.mitigating_factors,
            "citations": [c.to_dict() for c in self.citations],
            "recommendations": self.recommendations,
            "analyzed_at": self.analyzed_at.isoformat(),
        }


# ---------------------------------------------------------------------------
# Guideline limits (source of truth for quick eligibility checks)
# ---------------------------------------------------------------------------

AGENCY_LIMITS = {
    Agency.FANNIE_MAE: {
        "min_credit": 620,
        "max_dti": Decimal("50"),
        "max_ltv": {
            "primary": {"sfr": Decimal("97"), "condo": Decimal("97"), "2_unit": Decimal("85"), "3_unit": Decimal("75"), "4_unit": Decimal("75")},
            "second_home": {"sfr": Decimal("90"), "condo": Decimal("90")},
            "investment": {"sfr": Decimal("85"), "condo": Decimal("85"), "2_unit": Decimal("75"), "3_unit": Decimal("75"), "4_unit": Decimal("75")},
        },
        "max_loan": Decimal("766550"),
        "high_balance_max": Decimal("1149825"),
        "programs": ["Conventional 30yr", "Conventional 15yr", "HomeReady", "HFA Preferred"],
    },
    Agency.FREDDIE_MAC: {
        "min_credit": 620,
        "max_dti": Decimal("50"),
        "max_ltv": {
            "primary": {"sfr": Decimal("97"), "condo": Decimal("97"), "2_unit": Decimal("85"), "3_unit": Decimal("80"), "4_unit": Decimal("80")},
            "second_home": {"sfr": Decimal("90"), "condo": Decimal("90")},
            "investment": {"sfr": Decimal("85"), "condo": Decimal("85")},
        },
        "max_loan": Decimal("766550"),
        "high_balance_max": Decimal("1149825"),
        "programs": ["Home Possible", "HomeOne", "Standard"],
    },
    Agency.FHA: {
        "min_credit": 500,
        "max_dti": Decimal("57"),
        "max_ltv": {
            "primary": {"sfr": Decimal("96.5"), "condo": Decimal("96.5"), "2_unit": Decimal("96.5"), "3_unit": Decimal("96.5"), "4_unit": Decimal("96.5")},
        },
        "max_loan": Decimal("498257"),
        "high_balance_max": Decimal("1149825"),
        "min_credit_low_dp": 580,
        "programs": ["FHA 203(b)", "FHA 203(k) Standard", "FHA 203(k) Limited"],
    },
    Agency.VA: {
        "min_credit": 580,
        "max_dti": Decimal("60"),
        "max_ltv": {
            "primary": {"sfr": Decimal("100"), "condo": Decimal("100"), "2_unit": Decimal("100"), "3_unit": Decimal("100"), "4_unit": Decimal("100")},
        },
        "max_loan": None,
        "programs": ["VA Purchase", "VA IRRRL", "VA Cash-Out"],
    },
    Agency.USDA: {
        "min_credit": 640,
        "max_dti": Decimal("46"),
        "max_ltv": {
            "primary": {"sfr": Decimal("100")},
        },
        "max_loan": None,
        "income_limit": True,
        "programs": ["USDA Guaranteed", "USDA Direct"],
    },
}


WAITING_PERIODS = {
    Agency.FANNIE_MAE: {"bankruptcy_ch7": 48, "bankruptcy_ch13": 24, "foreclosure": 84, "short_sale": 48},
    Agency.FREDDIE_MAC: {"bankruptcy_ch7": 48, "bankruptcy_ch13": 24, "foreclosure": 84, "short_sale": 48},
    Agency.FHA: {"bankruptcy_ch7": 24, "bankruptcy_ch13": 12, "foreclosure": 36, "short_sale": 36},
    Agency.VA: {"bankruptcy_ch7": 24, "bankruptcy_ch13": 12, "foreclosure": 24, "short_sale": 24},
    Agency.USDA: {"bankruptcy_ch7": 36, "bankruptcy_ch13": 12, "foreclosure": 36, "short_sale": 36},
}


class UnderwriterCopilot:
    """
    Main copilot class that orchestrates eligibility checks, guideline lookups,
    and scenario analysis for LOs.
    """

    def __init__(self, db_session=None):
        self.db = db_session
        self._rag_service = None

    @property
    def rag_service(self) -> GuidelineRAGService:
        if self._rag_service is None:
            self._rag_service = GuidelineRAGService(db_session=self.db)
        return self._rag_service

    def analyze_scenario(self, scenario: BorrowerScenario, question: Optional[str] = None) -> CopilotAnalysis:
        ltv = self._calculate_ltv(scenario)
        dti = self._calculate_dti(scenario)

        eligible_programs = []
        ineligible_programs = []
        risk_factors = []
        mitigating_factors = []
        citations = []

        for agency, limits in AGENCY_LIMITS.items():
            result = self._check_agency_eligibility(agency, limits, scenario, ltv, dti)
            if result["eligible"]:
                eligible_programs.append(result)
            else:
                ineligible_programs.append(result)

        risk_factors = self._identify_risks(scenario, ltv, dti)
        mitigating_factors = self._identify_mitigants(scenario, ltv, dti)

        if question and self.db:
            try:
                rag_results = self.rag_service.query(question, top_k=5)
                citations = [
                    GuidelineCitation(
                        agency=r.agency,
                        section=r.section,
                        title=r.title,
                        excerpt=r.requirement,
                        relevance=r.relevance_score,
                    )
                    for r in rag_results
                ]
            except Exception as e:
                logger.warning(f"RAG lookup failed: {e}")

        confidence_score = self._calculate_confidence(
            eligible_programs, risk_factors, mitigating_factors, scenario
        )
        confidence = self._score_to_confidence(confidence_score)

        summary = self._generate_summary(
            scenario, eligible_programs, ineligible_programs,
            risk_factors, confidence, ltv, dti
        )

        recommendations = self._generate_recommendations(
            scenario, eligible_programs, ineligible_programs,
            risk_factors, ltv, dti
        )

        return CopilotAnalysis(
            question=question or f"Eligibility analysis for ${scenario.loan_amount:,.0f} loan",
            confidence=confidence,
            confidence_score=confidence_score,
            summary=summary,
            eligible_programs=eligible_programs,
            ineligible_programs=ineligible_programs,
            risk_factors=risk_factors,
            mitigating_factors=mitigating_factors,
            citations=citations,
            recommendations=recommendations,
        )

    def check_qualification(self, scenario: BorrowerScenario, target_agency: str) -> Dict[str, Any]:
        try:
            agency = Agency(target_agency)
        except ValueError:
            agency_map = {
                "fannie": Agency.FANNIE_MAE, "fnma": Agency.FANNIE_MAE,
                "freddie": Agency.FREDDIE_MAC, "fhlmc": Agency.FREDDIE_MAC,
                "fha": Agency.FHA, "va": Agency.VA, "usda": Agency.USDA,
            }
            agency = agency_map.get(target_agency.lower())
            if not agency:
                return {"error": f"Unknown agency: {target_agency}"}

        limits = AGENCY_LIMITS.get(agency, {})
        ltv = self._calculate_ltv(scenario)
        dti = self._calculate_dti(scenario)

        result = self._check_agency_eligibility(agency, limits, scenario, ltv, dti)
        result["ltv"] = float(ltv)
        result["dti"] = float(dti)
        return result

    def compare_programs(self, scenario: BorrowerScenario) -> List[Dict[str, Any]]:
        ltv = self._calculate_ltv(scenario)
        dti = self._calculate_dti(scenario)

        comparisons = []
        for agency, limits in AGENCY_LIMITS.items():
            result = self._check_agency_eligibility(agency, limits, scenario, ltv, dti)
            result["ltv"] = float(ltv)
            result["dti"] = float(dti)
            min_dp = self._calculate_min_down_payment(agency, scenario)
            result["min_down_payment"] = float(min_dp) if min_dp else None
            result["has_mi"] = ltv > Decimal("80") and agency in (Agency.FANNIE_MAE, Agency.FREDDIE_MAC)
            result["has_mip"] = agency == Agency.FHA
            result["has_funding_fee"] = agency == Agency.VA
            comparisons.append(result)

        comparisons.sort(key=lambda x: (not x["eligible"], -(x.get("issues_count", 0) or 0)))
        return comparisons

    # -----------------------------------------------------------------------
    # Private helpers
    # -----------------------------------------------------------------------

    def _calculate_ltv(self, scenario: BorrowerScenario) -> Decimal:
        if scenario.property_value <= 0:
            return Decimal("100")
        return (scenario.loan_amount / scenario.property_value * 100).quantize(Decimal("0.01"))

    def _calculate_dti(self, scenario: BorrowerScenario) -> Decimal:
        if scenario.annual_income <= 0:
            return Decimal("999")
        monthly_income = scenario.annual_income / 12
        return (scenario.monthly_debts / monthly_income * 100).quantize(Decimal("0.01"))

    def _check_agency_eligibility(
        self, agency: Agency, limits: Dict, scenario: BorrowerScenario,
        ltv: Decimal, dti: Decimal
    ) -> Dict[str, Any]:
        issues = []
        warnings = []
        programs = limits.get("programs", [])

        if agency == Agency.VA and not scenario.is_veteran:
            issues.append("VA loans require veteran/active military status")
        if agency == Agency.USDA and scenario.occupancy != "primary":
            issues.append("USDA requires primary residence")
        if agency == Agency.FHA and scenario.occupancy != "primary":
            issues.append("FHA requires primary residence")

        min_credit = limits.get("min_credit", 0)
        if scenario.credit_score < min_credit:
            issues.append(f"Credit score {scenario.credit_score} below {agency.value} minimum of {min_credit}")

        if agency == Agency.FHA and scenario.credit_score < 580:
            if ltv > Decimal("90"):
                issues.append("FHA with score below 580 requires 10% down (max 90% LTV)")

        max_dti = limits.get("max_dti", Decimal("100"))
        if dti > max_dti:
            issues.append(f"DTI {dti}% exceeds {agency.value} maximum of {max_dti}%")
        elif dti > max_dti - 5:
            warnings.append(f"DTI {dti}% is near the {agency.value} limit of {max_dti}%")

        occ = scenario.occupancy
        prop = scenario.property_type
        ltv_limits = limits.get("max_ltv", {})
        occ_limits = ltv_limits.get(occ, {})
        max_ltv = occ_limits.get(prop) or occ_limits.get("sfr")
        if max_ltv and ltv > max_ltv:
            issues.append(f"LTV {ltv}% exceeds {agency.value} max of {max_ltv}% for {occ}/{prop}")
        elif not occ_limits:
            issues.append(f"{agency.value} does not support {occ} occupancy")

        max_loan = limits.get("max_loan")
        if max_loan and scenario.loan_amount > max_loan:
            hb_max = limits.get("high_balance_max")
            if hb_max and scenario.loan_amount <= hb_max:
                warnings.append(f"Loan amount ${scenario.loan_amount:,.0f} exceeds conforming limit — high-balance pricing applies")
            elif hb_max:
                issues.append(f"Loan amount ${scenario.loan_amount:,.0f} exceeds {agency.value} high-balance limit of ${hb_max:,.0f}")
            else:
                issues.append(f"Loan amount ${scenario.loan_amount:,.0f} exceeds {agency.value} limit of ${max_loan:,.0f}")

        self._check_waiting_periods(agency, scenario, issues, warnings)

        return {
            "agency": agency.value,
            "agency_name": agency.name.replace("_", " ").title(),
            "programs": programs,
            "eligible": len(issues) == 0,
            "issues": issues,
            "issues_count": len(issues),
            "warnings": warnings,
        }

    def _check_waiting_periods(
        self, agency: Agency, scenario: BorrowerScenario,
        issues: List[str], warnings: List[str]
    ):
        periods = WAITING_PERIODS.get(agency, {})
        now = datetime.now(timezone.utc)

        if scenario.bankruptcy_date:
            months_since = (now.year - scenario.bankruptcy_date.year) * 12 + (now.month - scenario.bankruptcy_date.month)
            required = periods.get("bankruptcy_ch7", 48)
            if months_since < required:
                remaining = required - months_since
                issues.append(f"Bankruptcy waiting period: {remaining} months remaining ({agency.value} requires {required} months)")
            elif months_since < required + 12:
                warnings.append(f"Recently out of bankruptcy waiting period — may face tighter underwriting")

        if scenario.foreclosure_date:
            months_since = (now.year - scenario.foreclosure_date.year) * 12 + (now.month - scenario.foreclosure_date.month)
            required = periods.get("foreclosure", 84)
            if months_since < required:
                remaining = required - months_since
                issues.append(f"Foreclosure waiting period: {remaining} months remaining ({agency.value} requires {required} months)")

    def _identify_risks(self, scenario: BorrowerScenario, ltv: Decimal, dti: Decimal) -> List[str]:
        risks = []
        if scenario.credit_score < 640:
            risks.append(f"Low credit score ({scenario.credit_score}) — expect pricing adjustments and stricter conditions")
        if dti > Decimal("45"):
            risks.append(f"Elevated DTI ({dti}%) — compensating factors required")
        if ltv > Decimal("95"):
            risks.append(f"Very high LTV ({ltv}%) — limited program options")
        if scenario.self_employed and scenario.years_self_employed < 2:
            risks.append("Self-employed less than 2 years — most agencies require 2-year history")
        if scenario.months_reserves < 2:
            risks.append("Less than 2 months reserves — may not meet reserve requirements for investment/multi-unit")
        if scenario.property_type in ("3_unit", "4_unit") and scenario.occupancy == "investment":
            risks.append("Multi-unit investment property — tighter LTV limits and reserve requirements")
        return risks

    def _identify_mitigants(self, scenario: BorrowerScenario, ltv: Decimal, dti: Decimal) -> List[str]:
        mitigants = []
        if scenario.credit_score >= 740:
            mitigants.append(f"Strong credit ({scenario.credit_score}) — best pricing tier")
        if scenario.months_reserves >= 6:
            mitigants.append(f"{scenario.months_reserves} months reserves — strong compensating factor")
        if ltv <= Decimal("80"):
            mitigants.append("LTV at/below 80% — no private mortgage insurance required")
        if dti < Decimal("36"):
            mitigants.append(f"Conservative DTI ({dti}%) — well within guidelines")
        if scenario.is_first_time_buyer:
            mitigants.append("First-time buyer — eligible for special programs (HomeReady, Home Possible, FHA)")
        if scenario.is_veteran:
            mitigants.append("Veteran status — VA loan eligible (100% LTV, no MI)")
        return mitigants

    def _calculate_confidence(
        self, eligible_programs: List, risk_factors: List,
        mitigating_factors: List, scenario: BorrowerScenario
    ) -> float:
        base = 50.0
        base += min(len(eligible_programs) * 12, 36)
        base -= min(len(risk_factors) * 8, 24)
        base += min(len(mitigating_factors) * 5, 15)
        if scenario.credit_score >= 740:
            base += 10
        elif scenario.credit_score >= 680:
            base += 5
        elif scenario.credit_score < 620:
            base -= 15
        return max(0, min(100, base))

    def _score_to_confidence(self, score: float) -> ScenarioConfidence:
        if score >= 75:
            return ScenarioConfidence.HIGH
        if score >= 50:
            return ScenarioConfidence.MODERATE
        if score >= 25:
            return ScenarioConfidence.LOW
        return ScenarioConfidence.INELIGIBLE

    def _calculate_min_down_payment(self, agency: Agency, scenario: BorrowerScenario) -> Optional[Decimal]:
        limits = AGENCY_LIMITS.get(agency, {})
        ltv_limits = limits.get("max_ltv", {})
        occ_limits = ltv_limits.get(scenario.occupancy, {})
        max_ltv = occ_limits.get(scenario.property_type) or occ_limits.get("sfr")
        if not max_ltv:
            return None
        min_dp_pct = (100 - max_ltv) / 100
        return (scenario.property_value * min_dp_pct).quantize(Decimal("0.01"))

    def _generate_summary(
        self, scenario: BorrowerScenario, eligible: List, ineligible: List,
        risks: List, confidence: ScenarioConfidence, ltv: Decimal, dti: Decimal
    ) -> str:
        n_elig = len(eligible)
        if n_elig == 0:
            return (
                f"This borrower does not currently qualify for any standard agency programs. "
                f"Credit: {scenario.credit_score}, LTV: {ltv}%, DTI: {dti}%. "
                f"Consider non-QM options or address the eligibility issues listed below."
            )
        agency_names = ", ".join(p["agency_name"] for p in eligible[:3])
        return (
            f"Borrower is eligible for {n_elig} program{'s' if n_elig > 1 else ''} "
            f"({agency_names}). Credit: {scenario.credit_score}, LTV: {ltv}%, DTI: {dti}%. "
            f"Confidence: {confidence.value}. "
            f"{len(risks)} risk factor{'s' if len(risks) != 1 else ''} identified."
        )

    def _generate_recommendations(
        self, scenario: BorrowerScenario, eligible: List, ineligible: List,
        risks: List, ltv: Decimal, dti: Decimal
    ) -> List[str]:
        recs = []
        if ltv > Decimal("80") and any(p["agency"] in ("fnma", "fhlmc") for p in eligible):
            extra_dp = (scenario.loan_amount - scenario.property_value * Decimal("0.80")).quantize(Decimal("0.01"))
            if extra_dp > 0:
                recs.append(f"Increase down payment by ${extra_dp:,.0f} to reach 80% LTV and eliminate PMI")

        if scenario.credit_score < 740 and scenario.credit_score >= 680:
            recs.append("A credit score of 740+ would unlock best-execution pricing — review rapid rescore opportunities")

        va_elig = any(p["agency"] == "va" and p["eligible"] for p in eligible + ineligible)
        if scenario.is_veteran and not va_elig:
            recs.append("Verify VA entitlement — VA offers 100% LTV with no MI")

        if dti > Decimal("43") and dti <= Decimal("50"):
            monthly_reduction = ((dti - 43) / 100 * scenario.annual_income / 12).quantize(Decimal("0.01"))
            recs.append(f"Reducing monthly debts by ${monthly_reduction:,.0f} would bring DTI below 43% for broader eligibility")

        if scenario.months_reserves < 2:
            recs.append("Document at least 2 months of reserves — required for most investment/multi-unit scenarios")

        if not recs:
            recs.append("Borrower profile is strong — proceed with best-rate program option")

        return recs
