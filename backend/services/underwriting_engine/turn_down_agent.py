"""
Turn-Down Agent

Activates when DealBreakerRadar finds unresolvable hard stops.
Responsibilities:
1. Evaluate whether hard stops are truly unresolvable across ALL programs
2. Draft ECOA-compliant adverse action notice (Regulation B, 12 CFR 1002)
3. Route the notice to compliance officer for review
4. Log everything to the audit trail for regulatory examination

ECOA requires:
- Written notice within 30 days of adverse action
- Specific reason(s) for denial (not generic)
- Credit score disclosure when score was a factor
- Right to obtain a free credit report within 60 days

References:
- 12 CFR 1002.9 (ECOA adverse action notices)
- CFPB Regulation B (Equal Credit Opportunity)
- FCRA Section 615(a) (Credit score disclosure)
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Optional
import logging

from sqlalchemy.orm import Session

from .deal_breaker_radar import HardStop, HardStopType, Severity

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# ECOA adverse action reason codes
# ---------------------------------------------------------------------------

class AdverseActionReasonCode(str, Enum):
    """
    Standard adverse action reason codes from the ECOA/FCRA model forms.
    Codes map to hard-stop types for automated reason generation.
    """
    CREDIT_SCORE_INSUFFICIENT = "001"
    DTI_TOO_HIGH = "002"
    INSUFFICIENT_INCOME = "003"
    EMPLOYMENT_HISTORY_INSUFFICIENT = "004"
    COLLATERAL_INSUFFICIENT = "005"
    LTV_EXCESSIVE = "006"
    DEROGATORY_CREDIT_BANKRUPTCY = "007"
    DEROGATORY_CREDIT_FORECLOSURE = "008"
    COLLECTIONS_OUTSTANDING = "009"
    INCOME_DECLINING = "010"
    OCCUPANCY_MISREPRESENTATION = "011"
    FRAUD_SUSPECTED = "012"
    PROPERTY_INELIGIBLE = "013"
    PROGRAM_INELIGIBLE = "014"


# Map hard-stop types to ECOA reason codes
_HARD_STOP_TO_REASON: Dict[HardStopType, AdverseActionReasonCode] = {
    HardStopType.CREDIT_SCORE_BELOW_MIN: AdverseActionReasonCode.CREDIT_SCORE_INSUFFICIENT,
    HardStopType.DTI_EXCEEDED: AdverseActionReasonCode.DTI_TOO_HIGH,
    HardStopType.LTV_EXCEEDED: AdverseActionReasonCode.LTV_EXCESSIVE,
    HardStopType.BK_SEASONING: AdverseActionReasonCode.DEROGATORY_CREDIT_BANKRUPTCY,
    HardStopType.FORECLOSURE_SEASONING: AdverseActionReasonCode.DEROGATORY_CREDIT_FORECLOSURE,
    HardStopType.ACTIVE_COLLECTIONS: AdverseActionReasonCode.COLLECTIONS_OUTSTANDING,
    HardStopType.INCOME_DECLINING: AdverseActionReasonCode.INCOME_DECLINING,
    HardStopType.OCCUPANCY_MISREPRESENTATION: AdverseActionReasonCode.OCCUPANCY_MISREPRESENTATION,
    HardStopType.FRAUD_STRAW_BUYER: AdverseActionReasonCode.FRAUD_SUSPECTED,
    HardStopType.FRAUD_INFLATED_VALUE: AdverseActionReasonCode.FRAUD_SUSPECTED,
    HardStopType.FRAUD_UNDISCLOSED_LIABILITY: AdverseActionReasonCode.FRAUD_SUSPECTED,
    HardStopType.PROPERTY_INELIGIBLE: AdverseActionReasonCode.PROPERTY_INELIGIBLE,
    HardStopType.EMPLOYMENT_GAP: AdverseActionReasonCode.EMPLOYMENT_HISTORY_INSUFFICIENT,
}

# Human-readable descriptions for each reason code (for the borrower notice)
_REASON_DESCRIPTIONS: Dict[AdverseActionReasonCode, str] = {
    AdverseActionReasonCode.CREDIT_SCORE_INSUFFICIENT: (
        "Your credit score does not meet the minimum requirement for the loan program applied for."
    ),
    AdverseActionReasonCode.DTI_TOO_HIGH: (
        "Your total monthly debt obligations relative to your income exceed the "
        "maximum permitted ratio for the loan program applied for."
    ),
    AdverseActionReasonCode.INSUFFICIENT_INCOME: (
        "Your documented income is insufficient to support the requested loan amount."
    ),
    AdverseActionReasonCode.EMPLOYMENT_HISTORY_INSUFFICIENT: (
        "Your employment history does not demonstrate the stability or continuity "
        "required by the loan program guidelines."
    ),
    AdverseActionReasonCode.COLLATERAL_INSUFFICIENT: (
        "The collateral (property) does not meet the requirements for the requested financing."
    ),
    AdverseActionReasonCode.LTV_EXCESSIVE: (
        "The loan-to-value ratio exceeds the maximum allowed for the loan program and property type."
    ),
    AdverseActionReasonCode.DEROGATORY_CREDIT_BANKRUPTCY: (
        "A bankruptcy event on your credit report has not met the required waiting period "
        "for the loan program applied for."
    ),
    AdverseActionReasonCode.DEROGATORY_CREDIT_FORECLOSURE: (
        "A foreclosure, short sale, or deed-in-lieu event on your credit report has not met "
        "the required waiting period for the loan program applied for."
    ),
    AdverseActionReasonCode.COLLECTIONS_OUTSTANDING: (
        "You have outstanding collection accounts that exceed the permissible limits "
        "for the loan program applied for."
    ),
    AdverseActionReasonCode.INCOME_DECLINING: (
        "Your income history shows a significant declining trend that raises concerns "
        "about the ability to make future mortgage payments."
    ),
    AdverseActionReasonCode.OCCUPANCY_MISREPRESENTATION: (
        "The stated occupancy of the property could not be verified as consistent "
        "with the information provided in the application."
    ),
    AdverseActionReasonCode.FRAUD_SUSPECTED: (
        "Information provided in the application could not be verified and "
        "raised material concerns during the review process."
    ),
    AdverseActionReasonCode.PROPERTY_INELIGIBLE: (
        "The subject property does not meet the eligibility requirements "
        "for the loan program applied for."
    ),
    AdverseActionReasonCode.PROGRAM_INELIGIBLE: (
        "The application does not meet the eligibility requirements of the loan program."
    ),
}


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

class TurnDownDecision(str, Enum):
    """Outcome of the turn-down evaluation."""
    DENY = "deny"                      # Confirmed denial — generate adverse action
    REFER_ALTERNATIVE = "refer_alternative"  # Another program may work
    ESCALATE = "escalate"              # Needs human underwriter review
    HOLD = "hold"                      # Waivable stops — await compensating factors


@dataclass
class AdverseActionNotice:
    """ECOA-compliant adverse action notice."""
    loan_id: int
    notice_id: str
    borrower_name: str
    borrower_address: str
    application_date: str
    action_date: str
    lender_name: str
    lender_address: str
    lender_phone: str

    # Denial reasons (ECOA requires specific reasons, max 4 per model form)
    reason_codes: List[AdverseActionReasonCode] = field(default_factory=list)
    reason_descriptions: List[str] = field(default_factory=list)

    # Credit score disclosure (FCRA Section 615)
    credit_score: Optional[int] = None
    credit_score_range: Optional[str] = None
    credit_bureau: Optional[str] = None
    credit_score_factors: List[str] = field(default_factory=list)

    # Regulatory disclosures
    ecoa_notice: str = (
        "The Federal Equal Credit Opportunity Act prohibits creditors from discriminating "
        "against credit applicants on the basis of race, color, religion, national origin, "
        "sex, marital status, or age (provided the applicant has the capacity to enter into "
        "a binding contract); because all or part of the applicant's income derives from any "
        "public assistance program; or because the applicant has in good faith exercised any "
        "right under the Consumer Credit Protection Act."
    )
    credit_report_notice: str = (
        "You have the right to obtain a free copy of your credit report from the credit "
        "reporting agency identified above within 60 days of this notice."
    )

    status: str = "draft"  # draft, pending_review, approved, sent
    compliance_reviewer_id: Optional[int] = None
    reviewed_at: Optional[str] = None
    generated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "loan_id": self.loan_id,
            "notice_id": self.notice_id,
            "borrower_name": self.borrower_name,
            "borrower_address": self.borrower_address,
            "application_date": self.application_date,
            "action_date": self.action_date,
            "lender_name": self.lender_name,
            "lender_address": self.lender_address,
            "lender_phone": self.lender_phone,
            "reason_codes": [r.value for r in self.reason_codes],
            "reason_descriptions": self.reason_descriptions,
            "credit_score": self.credit_score,
            "credit_score_range": self.credit_score_range,
            "credit_bureau": self.credit_bureau,
            "credit_score_factors": self.credit_score_factors,
            "ecoa_notice": self.ecoa_notice,
            "credit_report_notice": self.credit_report_notice,
            "status": self.status,
            "compliance_reviewer_id": self.compliance_reviewer_id,
            "reviewed_at": self.reviewed_at,
            "generated_at": self.generated_at,
        }


@dataclass
class TurnDownResult:
    """Result of the turn-down agent evaluation."""
    loan_id: int
    decision: TurnDownDecision
    adverse_action_notice: Optional[AdverseActionNotice] = None
    alternative_programs: List[str] = field(default_factory=list)
    hard_stop_count: int = 0
    non_waivable_count: int = 0
    audit_entries: List[Dict[str, Any]] = field(default_factory=list)
    evaluated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "loan_id": self.loan_id,
            "decision": self.decision.value,
            "adverse_action_notice": (
                self.adverse_action_notice.to_dict()
                if self.adverse_action_notice else None
            ),
            "alternative_programs": self.alternative_programs,
            "hard_stop_count": self.hard_stop_count,
            "non_waivable_count": self.non_waivable_count,
            "audit_entries": self.audit_entries,
            "evaluated_at": self.evaluated_at,
        }


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------

class TurnDownAgent:
    """
    AI agent responsible for handling loan denials.

    When the DealBreakerRadar surfaces unresolvable hard stops, this agent:
    1. Determines if denial is truly the only path (or if alternatives exist)
    2. Generates an ECOA-compliant adverse action notice
    3. Routes the notice to a compliance officer for human review
    4. Creates an immutable audit trail for examination readiness

    Usage::

        agent = TurnDownAgent(lender_info={...})
        result = await agent.evaluate_and_act(loan_id, hard_stops, db)
    """

    def __init__(
        self,
        lender_info: Optional[Dict[str, str]] = None,
    ):
        """
        Args:
            lender_info: Dict with lender_name, lender_address, lender_phone.
                         Falls back to Perennia defaults if not provided.
        """
        self.lender_info = lender_info or {
            "lender_name": "Perennia AI Mortgage",
            "lender_address": "",
            "lender_phone": "",
        }

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def evaluate_and_act(
        self,
        loan_id: int,
        hard_stops: List[HardStop],
        db: Session,
    ) -> Dict[str, Any]:
        """
        Evaluate hard stops and take appropriate action.

        Args:
            loan_id: The loan record ID.
            hard_stops: List of HardStop objects from DealBreakerRadar.
            db: SQLAlchemy session for audit logging and loan lookup.

        Returns:
            Dict with decision, adverse_action_notice (if applicable), and audit info.
        """
        if not hard_stops:
            logger.info("TurnDownAgent: No hard stops for loan %s — no action needed.", loan_id)
            return TurnDownResult(
                loan_id=loan_id,
                decision=TurnDownDecision.HOLD,
            ).to_dict()

        non_waivable = [h for h in hard_stops if not h.is_waivable]
        critical = [h for h in hard_stops if h.severity == Severity.CRITICAL]
        waivable_only = len(non_waivable) == 0

        # --- Decision logic ---
        if waivable_only:
            decision = TurnDownDecision.ESCALATE
            logger.info(
                "TurnDownAgent: Loan %s has %d waivable hard stop(s) — escalating.",
                loan_id, len(hard_stops),
            )
        elif len(non_waivable) > 0 and len(critical) == 0:
            decision = TurnDownDecision.REFER_ALTERNATIVE
        else:
            decision = TurnDownDecision.DENY

        result = TurnDownResult(
            loan_id=loan_id,
            decision=decision,
            hard_stop_count=len(hard_stops),
            non_waivable_count=len(non_waivable),
        )

        # --- Generate adverse action notice for DENY ---
        if decision == TurnDownDecision.DENY:
            notice = await self.generate_adverse_action_notice(
                loan_id, hard_stops, db
            )
            result.adverse_action_notice = notice

            # Route to compliance officer
            await self._route_to_compliance(loan_id, notice, db)

        # --- Audit trail ---
        audit_entries = await self._create_audit_trail(
            loan_id, decision, hard_stops, result.adverse_action_notice, db
        )
        result.audit_entries = audit_entries

        logger.info(
            "TurnDownAgent: Loan %s — decision=%s, hard_stops=%d, non_waivable=%d",
            loan_id, decision.value, len(hard_stops), len(non_waivable),
        )

        return result.to_dict()

    async def generate_adverse_action_notice(
        self,
        loan_id: int,
        hard_stops: List[HardStop],
        db: Session,
    ) -> AdverseActionNotice:
        """
        Generate an ECOA-compliant adverse action notice.

        Args:
            loan_id: The loan record ID.
            hard_stops: List of HardStop objects triggering denial.
            db: SQLAlchemy session for looking up loan/borrower details.

        Returns:
            AdverseActionNotice in draft status, ready for compliance review.
        """
        # Fetch loan details
        loan_info = await self._fetch_loan_info(loan_id, db)

        # Map hard stops to ECOA reason codes (max 4 per model form)
        reason_codes: List[AdverseActionReasonCode] = []
        reason_descriptions: List[str] = []
        seen_codes: set = set()

        # Prioritize non-waivable / critical stops first
        sorted_stops = sorted(
            hard_stops,
            key=lambda h: (
                0 if h.severity == Severity.CRITICAL else
                1 if h.severity == Severity.HIGH else 2,
                0 if not h.is_waivable else 1,
            ),
        )

        for stop in sorted_stops:
            code = _HARD_STOP_TO_REASON.get(stop.type)
            if code and code not in seen_codes:
                seen_codes.add(code)
                reason_codes.append(code)
                description = _REASON_DESCRIPTIONS.get(code, stop.description)
                reason_descriptions.append(description)
            if len(reason_codes) >= 4:
                break

        # Build credit score disclosure if applicable
        credit_score = loan_info.get("credit_score")
        credit_bureau = loan_info.get("credit_bureau", "Equifax, Experian, or TransUnion")
        credit_factors = loan_info.get("credit_score_factors", [])

        now = datetime.now(timezone.utc)
        notice_id = f"AAN-{loan_id}-{now.strftime('%Y%m%d%H%M%S')}"

        notice = AdverseActionNotice(
            loan_id=loan_id,
            notice_id=notice_id,
            borrower_name=loan_info.get("borrower_name", ""),
            borrower_address=loan_info.get("borrower_address", ""),
            application_date=loan_info.get("application_date", ""),
            action_date=now.strftime("%Y-%m-%d"),
            lender_name=self.lender_info.get("lender_name", ""),
            lender_address=self.lender_info.get("lender_address", ""),
            lender_phone=self.lender_info.get("lender_phone", ""),
            reason_codes=reason_codes,
            reason_descriptions=reason_descriptions,
            credit_score=credit_score,
            credit_score_range="300-850" if credit_score else None,
            credit_bureau=credit_bureau if credit_score else None,
            credit_score_factors=credit_factors,
            status="draft",
        )

        logger.info(
            "TurnDownAgent: Generated adverse action notice %s for loan %s with %d reason(s).",
            notice_id, loan_id, len(reason_codes),
        )

        return notice

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _fetch_loan_info(self, loan_id: int, db: Session) -> Dict[str, Any]:
        """
        Look up loan and borrower details from the database.
        Uses lazy import to avoid circular dependency.
        """
        try:
            from database.models.lead_loan import Loan
            loan = db.query(Loan).filter(Loan.id == loan_id).first()
            if loan:
                return {
                    "borrower_name": getattr(loan, "borrower_name", ""),
                    "borrower_address": getattr(loan, "property_address", ""),
                    "application_date": (
                        loan.application_date.isoformat()
                        if getattr(loan, "application_date", None) else ""
                    ),
                    "credit_score": getattr(loan, "credit_score", None),
                    "credit_bureau": "Equifax, Experian, and TransUnion",
                    "credit_score_factors": [],
                }
        except Exception as e:
            logger.exception("TurnDownAgent: Failed to fetch loan %s: %s", loan_id, e)

        return {
            "borrower_name": "",
            "borrower_address": "",
            "application_date": "",
            "credit_score": None,
        }

    async def _route_to_compliance(
        self,
        loan_id: int,
        notice: AdverseActionNotice,
        db: Session,
    ) -> None:
        """
        Create a compliance review task for the adverse action notice.
        The notice stays in 'draft' status until a compliance officer approves it.
        """
        try:
            from database.models.security import AuditLog

            audit_entry = AuditLog(
                change_type="compliance_review",
                entity_type="adverse_action_notice",
                entity_id=loan_id,
                before_state=None,
                after_state={
                    "notice_id": notice.notice_id,
                    "status": "pending_review",
                    "reason_codes": [r.value for r in notice.reason_codes],
                },
                reason=(
                    f"Adverse action notice {notice.notice_id} routed to compliance "
                    f"for review — {len(notice.reason_codes)} denial reason(s)."
                ),
                timestamp=datetime.now(timezone.utc),
            )
            db.add(audit_entry)
            db.flush()

            logger.info(
                "TurnDownAgent: Routed notice %s to compliance review.", notice.notice_id,
            )
        except Exception as e:
            logger.exception(
                "TurnDownAgent: Failed to route notice %s to compliance: %s",
                notice.notice_id, e,
            )

    async def _create_audit_trail(
        self,
        loan_id: int,
        decision: TurnDownDecision,
        hard_stops: List[HardStop],
        notice: Optional[AdverseActionNotice],
        db: Session,
    ) -> List[Dict[str, Any]]:
        """
        Create immutable audit log entries for the turn-down evaluation.
        Returns the entries as dicts for inclusion in the result.
        """
        entries: List[Dict[str, Any]] = []

        try:
            from database.models.security import AuditLog

            # Entry 1: The evaluation decision
            eval_entry = AuditLog(
                change_type="underwriting_decision",
                entity_type="loan",
                entity_id=loan_id,
                before_state=None,
                after_state={
                    "decision": decision.value,
                    "hard_stop_count": len(hard_stops),
                    "hard_stop_types": [h.type.value for h in hard_stops],
                    "non_waivable_count": sum(1 for h in hard_stops if not h.is_waivable),
                },
                reason=f"TurnDownAgent evaluated loan {loan_id}: decision={decision.value}",
                timestamp=datetime.now(timezone.utc),
            )
            db.add(eval_entry)
            entries.append({
                "type": "underwriting_decision",
                "decision": decision.value,
                "hard_stop_count": len(hard_stops),
            })

            # Entry 2: Each hard stop recorded individually for examination trail
            for stop in hard_stops:
                stop_entry = AuditLog(
                    change_type="hard_stop_finding",
                    entity_type="loan",
                    entity_id=loan_id,
                    before_state=None,
                    after_state=stop.to_dict(),
                    reason=(
                        f"Hard stop: {stop.type.value} — {stop.description}"
                    ),
                    timestamp=datetime.now(timezone.utc),
                )
                db.add(stop_entry)
                entries.append({
                    "type": "hard_stop_finding",
                    "hard_stop_type": stop.type.value,
                    "severity": stop.severity.value,
                })

            # Entry 3: Adverse action notice generation (if applicable)
            if notice:
                notice_entry = AuditLog(
                    change_type="adverse_action_generated",
                    entity_type="adverse_action_notice",
                    entity_id=loan_id,
                    before_state=None,
                    after_state={
                        "notice_id": notice.notice_id,
                        "reason_codes": [r.value for r in notice.reason_codes],
                        "status": notice.status,
                    },
                    reason=(
                        f"Adverse action notice {notice.notice_id} generated "
                        f"for loan {loan_id}."
                    ),
                    timestamp=datetime.now(timezone.utc),
                )
                db.add(notice_entry)
                entries.append({
                    "type": "adverse_action_generated",
                    "notice_id": notice.notice_id,
                })

            db.flush()

        except Exception as e:
            logger.exception(
                "TurnDownAgent: Failed to create audit trail for loan %s: %s",
                loan_id, e,
            )

        return entries
