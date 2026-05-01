"""
Real-Time Pipeline Decisioning Service

For every loan in pipeline, provides:
- Next best action
- Compliance risk score
- Predicted close probability
- Recommended outreach

Combines Pipeline Coach + Compliance Sentry + Calculator insights.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Optional
import logging

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


class ActionPriority(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class ActionCategory(str, Enum):
    COMPLIANCE = "compliance"
    FOLLOW_UP = "follow_up"
    DOCUMENT = "document"
    RATE_LOCK = "rate_lock"
    MILESTONE = "milestone"
    OUTREACH = "outreach"
    RISK = "risk"


@dataclass
class NextBestAction:
    action: str
    category: ActionCategory
    priority: ActionPriority
    reason: str
    due_by: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "action": self.action,
            "category": self.category.value,
            "priority": self.priority.value,
            "reason": self.reason,
            "due_by": self.due_by.isoformat() if self.due_by else None,
        }


@dataclass
class LoanDecision:
    loan_id: str
    borrower_name: str
    loan_amount: float
    stage: str
    days_in_stage: int
    close_probability: float
    compliance_risk_score: float
    next_actions: List[NextBestAction]
    recommended_outreach: Optional[str]
    alerts: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "loan_id": self.loan_id,
            "borrower_name": self.borrower_name,
            "loan_amount": self.loan_amount,
            "stage": self.stage,
            "days_in_stage": self.days_in_stage,
            "close_probability": round(self.close_probability, 1),
            "compliance_risk_score": round(self.compliance_risk_score, 1),
            "next_actions": [a.to_dict() for a in self.next_actions],
            "recommended_outreach": self.recommended_outreach,
            "alerts": self.alerts,
        }


# Stage progression weights for close probability
STAGE_CLOSE_WEIGHTS = {
    "APPLICATION": 15,
    "DISCLOSED": 25,
    "PROCESSING": 35,
    "SUBMITTED": 45,
    "UNDERWRITING": 50,
    "UW_RECEIVED": 55,
    "CONDITIONAL_APPROVAL": 70,
    "APPROVED": 80,
    "SUSPENDED": 30,
    "CTC": 85,
    "CLEAR_TO_CLOSE": 90,
    "CLOSING": 92,
    "DOCS": 94,
    "DOCS_OUT": 96,
}

# Max days before a stage is considered stale
STAGE_SLA_DAYS = {
    "APPLICATION": 3,
    "DISCLOSED": 5,
    "PROCESSING": 7,
    "SUBMITTED": 3,
    "UNDERWRITING": 5,
    "UW_RECEIVED": 2,
    "CONDITIONAL_APPROVAL": 7,
    "APPROVED": 3,
    "CTC": 3,
    "CLEAR_TO_CLOSE": 5,
    "CLOSING": 3,
    "DOCS": 3,
    "DOCS_OUT": 5,
}

TERMINAL_STAGES = {"FUNDED", "CANCELLED", "DENIED", "DEAD", "WITHDRAWN", "DOES_NOT_QUALIFY", "NURTURE"}


class PipelineDecisioningService:

    def __init__(self, db: Session, org_id: str, user_id: str):
        self.db = db
        self.org_id = org_id
        self.user_id = user_id

    def get_pipeline_decisions(self, limit: int = 50) -> List[LoanDecision]:
        loans = self._fetch_active_loans(limit)
        decisions = []

        for loan in loans:
            decision = self._analyze_loan(loan)
            decisions.append(decision)

        decisions.sort(key=lambda d: (
            -len([a for a in d.next_actions if a.priority == ActionPriority.CRITICAL]),
            -d.compliance_risk_score,
            d.close_probability,
        ))

        return decisions

    def get_dashboard_summary(self) -> Dict[str, Any]:
        decisions = self.get_pipeline_decisions(limit=200)

        total = len(decisions)
        if total == 0:
            return {
                "total_loans": 0,
                "avg_close_probability": 0,
                "avg_compliance_risk": 0,
                "critical_actions": 0,
                "stale_loans": 0,
                "projected_funded": 0,
                "stage_distribution": {},
            }

        critical_count = sum(
            1 for d in decisions
            if any(a.priority == ActionPriority.CRITICAL for a in d.next_actions)
        )
        stale_count = sum(
            1 for d in decisions
            if d.days_in_stage > STAGE_SLA_DAYS.get(d.stage, 7)
        )
        avg_prob = sum(d.close_probability for d in decisions) / total
        avg_risk = sum(d.compliance_risk_score for d in decisions) / total
        projected = sum(d.loan_amount * d.close_probability / 100 for d in decisions)

        stage_dist = {}
        for d in decisions:
            stage_dist[d.stage] = stage_dist.get(d.stage, 0) + 1

        return {
            "total_loans": total,
            "avg_close_probability": round(avg_prob, 1),
            "avg_compliance_risk": round(avg_risk, 1),
            "critical_actions": critical_count,
            "stale_loans": stale_count,
            "projected_funded": round(projected, 2),
            "stage_distribution": stage_dist,
        }

    def _fetch_active_loans(self, limit: int) -> List[Any]:
        try:
            result = self.db.execute(
                text("""
                    SELECT l.id, l.loan_number, l.loan_amount, l.stage,
                           l.stage_updated_at, l.created_at, l.lock_expiration_date,
                           l.property_address, l.loan_type,
                           ld.first_name, ld.last_name, ld.email, ld.phone
                    FROM loans l
                    LEFT JOIN leads ld ON l.lead_id = ld.id
                    WHERE l.org_id = :org_id
                    AND l.assigned_to = :user_id
                    AND UPPER(COALESCE(l.stage, '')) NOT IN :terminal
                    AND (l.deleted_at IS NULL)
                    ORDER BY l.stage_updated_at ASC NULLS FIRST
                    LIMIT :limit
                """),
                {
                    "org_id": self.org_id,
                    "user_id": self.user_id,
                    "terminal": tuple(TERMINAL_STAGES),
                    "limit": limit,
                },
            )
            return result.fetchall()
        except Exception as e:
            logger.error(f"Failed to fetch active loans: {e}")
            return []

    def _analyze_loan(self, loan) -> LoanDecision:
        stage = (getattr(loan, "stage", "") or "").upper()
        stage_updated = getattr(loan, "stage_updated_at", None) or getattr(loan, "created_at", None)
        now = datetime.now(timezone.utc)

        if stage_updated:
            if stage_updated.tzinfo is None:
                stage_updated = stage_updated.replace(tzinfo=timezone.utc)
            days_in_stage = (now - stage_updated).days
        else:
            days_in_stage = 0

        close_prob = self._calculate_close_probability(stage, days_in_stage, loan)
        compliance_risk = self._calculate_compliance_risk(stage, loan, days_in_stage)
        actions = self._generate_actions(stage, loan, days_in_stage)
        outreach = self._recommend_outreach(stage, loan, days_in_stage)
        alerts = self._generate_alerts(stage, loan, days_in_stage)

        first = getattr(loan, "first_name", "") or ""
        last = getattr(loan, "last_name", "") or ""
        borrower_name = f"{first} {last}".strip() or "Unknown"

        return LoanDecision(
            loan_id=str(loan.id),
            borrower_name=borrower_name,
            loan_amount=float(getattr(loan, "loan_amount", 0) or 0),
            stage=stage,
            days_in_stage=days_in_stage,
            close_probability=close_prob,
            compliance_risk_score=compliance_risk,
            next_actions=actions,
            recommended_outreach=outreach,
            alerts=alerts,
        )

    def _calculate_close_probability(self, stage: str, days_in_stage: int, loan) -> float:
        base = STAGE_CLOSE_WEIGHTS.get(stage, 10)
        sla = STAGE_SLA_DAYS.get(stage, 7)
        if days_in_stage > sla * 2:
            base *= 0.7
        elif days_in_stage > sla:
            base *= 0.85
        return max(0, min(100, base))

    def _calculate_compliance_risk(self, stage: str, loan, days_in_stage: int) -> float:
        risk = 10.0

        if stage == "DISCLOSED":
            if days_in_stage > 3:
                risk += 20
        if stage in ("APPLICATION", "DISCLOSED") and days_in_stage > 10:
            risk += 15

        lock_exp = getattr(loan, "lock_expiration_date", None)
        if lock_exp:
            if isinstance(lock_exp, datetime):
                if lock_exp.tzinfo is None:
                    lock_exp = lock_exp.replace(tzinfo=timezone.utc)
                days_to_expiry = (lock_exp - datetime.now(timezone.utc)).days
                if days_to_expiry < 0:
                    risk += 30
                elif days_to_expiry < 7:
                    risk += 15
                elif days_to_expiry < 14:
                    risk += 5

        if stage == "CONDITIONAL_APPROVAL" and days_in_stage > 14:
            risk += 10

        return min(100, risk)

    def _generate_actions(self, stage: str, loan, days_in_stage: int) -> List[NextBestAction]:
        actions = []
        now = datetime.now(timezone.utc)
        sla = STAGE_SLA_DAYS.get(stage, 7)

        if days_in_stage > sla:
            actions.append(NextBestAction(
                action=f"Loan stale in {stage} for {days_in_stage} days (SLA: {sla}d)",
                category=ActionCategory.MILESTONE,
                priority=ActionPriority.HIGH if days_in_stage > sla * 2 else ActionPriority.MEDIUM,
                reason="Stage SLA exceeded — follow up with processor/underwriter",
            ))

        lock_exp = getattr(loan, "lock_expiration_date", None)
        if lock_exp and isinstance(lock_exp, datetime):
            if lock_exp.tzinfo is None:
                lock_exp = lock_exp.replace(tzinfo=timezone.utc)
            days_to_expiry = (lock_exp - now).days
            if days_to_expiry < 0:
                actions.append(NextBestAction(
                    action="Rate lock EXPIRED — extend or re-lock immediately",
                    category=ActionCategory.RATE_LOCK,
                    priority=ActionPriority.CRITICAL,
                    reason="Expired lock may require new pricing and re-disclosure",
                ))
            elif days_to_expiry < 7:
                actions.append(NextBestAction(
                    action=f"Rate lock expires in {days_to_expiry} days — verify closing timeline",
                    category=ActionCategory.RATE_LOCK,
                    priority=ActionPriority.HIGH,
                    reason="Lock extension fees apply if not closed in time",
                    due_by=lock_exp,
                ))

        if stage == "APPLICATION":
            actions.append(NextBestAction(
                action="Send initial disclosures within 3 business days",
                category=ActionCategory.COMPLIANCE,
                priority=ActionPriority.HIGH if days_in_stage >= 2 else ActionPriority.MEDIUM,
                reason="TRID requires LE within 3 business days of application",
                due_by=now + timedelta(days=max(0, 3 - days_in_stage)),
            ))
        elif stage == "CONDITIONAL_APPROVAL":
            actions.append(NextBestAction(
                action="Review and clear outstanding conditions",
                category=ActionCategory.DOCUMENT,
                priority=ActionPriority.HIGH,
                reason="Conditions must be cleared for CTC",
            ))
        elif stage == "CLEAR_TO_CLOSE":
            actions.append(NextBestAction(
                action="Schedule closing and send CD",
                category=ActionCategory.MILESTONE,
                priority=ActionPriority.HIGH,
                reason="CD must be delivered 3 days before closing (TRID)",
            ))

        actions.sort(key=lambda a: ["critical", "high", "medium", "low"].index(a.priority.value))
        return actions

    def _recommend_outreach(self, stage: str, loan, days_in_stage: int) -> Optional[str]:
        borrower_name = getattr(loan, "first_name", "the borrower") or "the borrower"

        if stage in ("APPLICATION", "DISCLOSED") and days_in_stage >= 3:
            return f"Call {borrower_name} — confirm application details and set expectations for processing timeline"
        if stage == "PROCESSING" and days_in_stage >= 5:
            return f"Text {borrower_name} — processing update, request any outstanding documents"
        if stage == "UNDERWRITING" and days_in_stage >= 3:
            return f"Email {borrower_name} — loan is in underwriting, expected turnaround 2-3 days"
        if stage == "CONDITIONAL_APPROVAL":
            return f"Call {borrower_name} — review conditions, collect needed items"
        if stage == "CLEAR_TO_CLOSE":
            return f"Call {borrower_name} — congratulations! Schedule closing appointment"
        if stage == "SUSPENDED" and days_in_stage >= 2:
            return f"Call {borrower_name} — discuss suspension reason and path forward"
        return None

    def _generate_alerts(self, stage: str, loan, days_in_stage: int) -> List[str]:
        alerts = []
        sla = STAGE_SLA_DAYS.get(stage, 7)

        if days_in_stage > sla * 3:
            alerts.append(f"STALE: {days_in_stage} days in {stage} (3x SLA)")
        if stage == "SUSPENDED":
            alerts.append("Loan SUSPENDED — requires immediate attention")
        if stage == "APPLICATION" and days_in_stage >= 3:
            alerts.append("TRID deadline approaching — initial disclosures due")

        return alerts
