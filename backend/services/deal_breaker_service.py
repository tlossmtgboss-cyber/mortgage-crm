"""Deal Breaker Radar — deterministic rules engine for mortgage disqualification detection."""
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


@dataclass
class DealBreaker:
    name: str
    reason: str
    remediation: str
    severity: str  # "hard" (cannot proceed) or "soft" (alternative path exists)
    category: str  # credit, income, property, ltvdti, regulatory


@dataclass
class DealBreakerResult:
    lead_id: str
    has_deal_breakers: bool
    deal_breakers: List[DealBreaker] = field(default_factory=list)
    eligible_programs: List[str] = field(default_factory=list)
    recommended_action: str = ""  # proceed, alternative_path, nurture, disqualify
    evaluation_id: str = field(default_factory=lambda: str(uuid.uuid4())[:12].upper())
    evaluated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "lead_id": self.lead_id,
            "has_deal_breakers": self.has_deal_breakers,
            "deal_breakers": [
                {"name": db.name, "reason": db.reason, "remediation": db.remediation,
                 "severity": db.severity, "category": db.category}
                for db in self.deal_breakers
            ],
            "eligible_programs": self.eligible_programs,
            "recommended_action": self.recommended_action,
            "evaluation_id": self.evaluation_id,
            "evaluated_at": self.evaluated_at,
        }


class DealBreakerService:
    """Evaluates borrower data against deal-breaker rules."""

    def evaluate(self, borrower_data: Dict[str, Any]) -> DealBreakerResult:
        """Evaluate borrower for deal breakers. Returns structured result."""
        lead_id = borrower_data.get("lead_id", "unknown")
        breakers = []

        # --- CREDIT RULES ---
        credit_score = borrower_data.get("credit_score")
        if credit_score is not None:
            if credit_score < 500:
                breakers.append(DealBreaker(
                    name="credit_below_minimum",
                    reason=f"Credit score {credit_score} is below all program minimums (500)",
                    remediation="Refer to credit repair partner. Re-engage in 6-12 months after score improvement.",
                    severity="hard",
                    category="credit",
                ))
            elif credit_score < 580:
                breakers.append(DealBreaker(
                    name="credit_fha_10pct_only",
                    reason=f"Credit score {credit_score} requires 10% down payment for FHA",
                    remediation="FHA with 10% down is available. Conventional/VA/USDA require higher scores. Consider credit repair for more options.",
                    severity="soft",
                    category="credit",
                ))

        # --- BANKRUPTCY ---
        bankruptcy_years = borrower_data.get("years_since_bankruptcy")
        if bankruptcy_years is not None:
            bankruptcy_type = borrower_data.get("bankruptcy_type", "chapter_7")
            if bankruptcy_type == "chapter_7" and bankruptcy_years < 2:
                breakers.append(DealBreaker(
                    name="recent_bankruptcy_ch7",
                    reason=f"Chapter 7 bankruptcy {bankruptcy_years} year(s) ago",
                    remediation=f"Waiting periods: FHA/VA = 2 years, Conventional = 4 years. Eligible for FHA in {2 - bankruptcy_years} year(s).",
                    severity="hard",
                    category="credit",
                ))
            elif bankruptcy_type == "chapter_13" and bankruptcy_years < 1:
                breakers.append(DealBreaker(
                    name="recent_bankruptcy_ch13",
                    reason=f"Chapter 13 bankruptcy {bankruptcy_years} year(s) ago",
                    remediation="FHA/VA eligible 1 year into repayment plan with court approval. Conventional requires 2 years from discharge.",
                    severity="hard",
                    category="credit",
                ))

        # --- FORECLOSURE ---
        foreclosure_years = borrower_data.get("years_since_foreclosure")
        if foreclosure_years is not None and foreclosure_years < 3:
            breakers.append(DealBreaker(
                name="recent_foreclosure",
                reason=f"Foreclosure {foreclosure_years} year(s) ago",
                remediation=f"Waiting periods: FHA = 3 years, VA = 2 years, Conventional = 7 years. Earliest eligibility in {max(0, 2 - foreclosure_years)} year(s) (VA).",
                severity="hard",
                category="credit",
            ))

        # --- INCOME RULES ---
        employment_type = borrower_data.get("employment_type", "").lower()
        years_employed = borrower_data.get("years_in_current_employment")
        if employment_type in ("self_employed", "self-employed", "1099"):
            if years_employed is not None and years_employed < 2:
                breakers.append(DealBreaker(
                    name="self_employed_under_2yr",
                    reason=f"Self-employment history {years_employed} year(s) — most programs require 2 years",
                    remediation="Explore 1-year bank statement programs (Non-QM). Or wait until 2-year mark for conventional/FHA eligibility.",
                    severity="soft",
                    category="income",
                ))

        income_verifiable = borrower_data.get("income_verifiable")
        if income_verifiable is False:
            breakers.append(DealBreaker(
                name="no_verifiable_income",
                reason="Cannot verify income through standard documentation",
                remediation="Explore bank statement loan programs (12-24 month statements), asset depletion loans, or DSCR loans for investment properties.",
                severity="soft",
                category="income",
            ))

        # --- PROPERTY RULES ---
        property_type = borrower_data.get("property_type", "").lower()
        if property_type in ("manufactured", "mobile_home"):
            breakers.append(DealBreaker(
                name="manufactured_home_restrictions",
                reason="Manufactured/mobile homes have limited financing options",
                remediation="FHA Title II available if on permanent foundation. VA and USDA may be options. Chattel loans for non-permanent.",
                severity="soft",
                category="property",
            ))

        property_state = borrower_data.get("property_state", "").upper()
        licensed_states = borrower_data.get("licensed_states", [])
        if property_state and licensed_states and property_state not in licensed_states:
            breakers.append(DealBreaker(
                name="unlicensed_state",
                reason=f"Not licensed to originate in {property_state}",
                remediation=f"Refer to partner lender licensed in {property_state}.",
                severity="hard",
                category="regulatory",
            ))

        # --- LTV / DTI RULES ---
        ltv = borrower_data.get("ltv")
        if ltv is not None and ltv > 100:
            breakers.append(DealBreaker(
                name="ltv_exceeds_maximum",
                reason=f"LTV {ltv}% exceeds all program limits",
                remediation="Explore VA (100% LTV), USDA (100% LTV), or down payment assistance programs. Conventional requires ≤97% LTV.",
                severity="soft",
                category="ltvdti",
            ))

        dti = borrower_data.get("dti")
        if dti is not None and dti > 57:
            breakers.append(DealBreaker(
                name="dti_exceeds_maximum",
                reason=f"DTI {dti}% exceeds all program maximums (FHA max 57%)",
                remediation="Discuss debt payoff strategies, co-borrower options, or income growth timeline. Revisit when DTI is below 50%.",
                severity="hard",
                category="ltvdti",
            ))

        # --- CITIZENSHIP ---
        citizenship = borrower_data.get("citizenship_status", "").lower()
        if citizenship in ("non_resident_alien", "undocumented", "no_ssn"):
            breakers.append(DealBreaker(
                name="non_resident_alien",
                reason="Non-resident alien or no SSN/ITIN",
                remediation="Explore ITIN loan programs (Non-QM), foreign national programs, or obtain ITIN through IRS before applying.",
                severity="soft",
                category="regulatory",
            ))

        # --- DETERMINE RESULT ---
        hard_breakers = [b for b in breakers if b.severity == "hard"]
        soft_breakers = [b for b in breakers if b.severity == "soft"]

        if hard_breakers:
            action = "disqualify" if not soft_breakers else "nurture"
        elif soft_breakers:
            action = "alternative_path"
        else:
            action = "proceed"

        # Determine eligible programs
        eligible = self._get_eligible_programs(borrower_data, breakers)

        return DealBreakerResult(
            lead_id=lead_id,
            has_deal_breakers=len(breakers) > 0,
            deal_breakers=breakers,
            eligible_programs=eligible,
            recommended_action=action,
        )

    def evaluate_lead(self, db: Session, lead_id: str) -> DealBreakerResult:
        """Evaluate a lead by ID, pulling data from the database."""
        try:
            from database.models.lead_loan import Lead
            lead = db.query(Lead).filter(Lead.id == lead_id).first()
            if not lead:
                result = DealBreakerResult(lead_id=lead_id, has_deal_breakers=False)
                result.recommended_action = "not_found"
                return result

            borrower_data = {
                "lead_id": lead_id,
                "credit_score": lead.credit_score if hasattr(lead, "credit_score") else None,
                "employment_type": getattr(lead, "employment_status", None) or "",
                "property_type": getattr(lead, "property_type", None) or "",
                "property_state": getattr(lead, "state", None) or "",
                "dti": getattr(lead, "dti", None),
                "ltv": getattr(lead, "ltv", None),
                "loan_amount": getattr(lead, "loan_amount", None),
            }
            return self.evaluate(borrower_data)
        except Exception:
            logger.exception(f"Failed to evaluate lead {lead_id}")
            result = DealBreakerResult(lead_id=lead_id, has_deal_breakers=False)
            result.recommended_action = "error"
            return result

    def _get_eligible_programs(self, data: Dict, breakers: List[DealBreaker]) -> List[str]:
        """Determine which loan programs the borrower might still qualify for."""
        programs = []
        credit = data.get("credit_score") or 0
        breaker_names = {b.name for b in breakers}

        if credit >= 620 and "recent_bankruptcy_ch7" not in breaker_names:
            programs.append("conventional")
        if credit >= 580:
            programs.append("fha")
        elif credit >= 500:
            programs.append("fha_10pct_down")
        if credit >= 620 and data.get("is_veteran"):
            programs.append("va")
        if credit >= 640 and data.get("is_rural"):
            programs.append("usda")
        if credit >= 700:
            programs.append("jumbo")
        if credit >= 600:
            programs.append("non_qm")

        return programs


# Module-level singleton
_service = None


def get_deal_breaker_service() -> DealBreakerService:
    global _service
    if _service is None:
        _service = DealBreakerService()
    return _service
