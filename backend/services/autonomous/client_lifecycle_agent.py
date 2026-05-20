"""Client Lifecycle Agent — post-closing relationship management for funded loans.

Identifies milestone anniversaries, refinance opportunities, and optimal referral
request timing. Runs on a schedule via the autonomous agent framework.
"""

import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from database.models.lead_loan import Lead, Loan
from database.models.communication import Activity
from database.models.security import Notification
from database.models.rate_lock import RateMarketData
from database.enums import ActivityType

logger = logging.getLogger(__name__)

FUNDED_STAGES = frozenset({"FUNDED"})
_DEFAULT_REFI_THRESHOLD = Decimal("0.5")  # percentage points
_REFERRAL_WINDOW = (90, 180)  # days post-funded_date
_MILESTONE_TOLERANCE_DAYS = 3

# Milestone message templates keyed by milestone_type
_MILESTONE_MESSAGES = {
    "1-month check-in": (
        "Hi {name}, congratulations on your first month in your new home! "
        "Settling in? Let us know if you need anything."
    ),
    "3-month check-in": (
        "Hi {name}, hope you're enjoying your home! "
        "Quick check — any questions about your mortgage?"
    ),
    "6-month check-in": (
        "Hi {name}, can you believe it's already been 6 months? "
        "If you've made improvements, your home value may have changed. "
        "Let us know if you'd like a quick equity check."
    ),
    "1-year anniversary": (
        "Happy home anniversary, {name}! It's been a year since closing. "
        "Here's a great time for a quick review of your equity position "
        "and to make sure your mortgage is still working for you."
    ),
    "2-year anniversary": (
        "Happy 2-year anniversary, {name}! A lot can change in two years. "
        "Would you like us to review your current rate and equity?"
    ),
    "3-year anniversary": (
        "Hi {name}, 3 years in your home — congratulations! "
        "With the equity you've built, there may be new options available. "
        "Let's schedule a quick review."
    ),
}


class ClientLifecycleAgent:
    """Scans funded loans for milestones, refi opportunities, and referral candidates."""

    AGENT_TYPE = "client_lifecycle"
    MILESTONE_DAYS = {
        30: "1-month check-in",
        90: "3-month check-in",
        180: "6-month check-in",
        365: "1-year anniversary",
        730: "2-year anniversary",
        1095: "3-year anniversary",
    }

    def __init__(self, db: Session, org_id: int, config: dict | None = None, gateway=None):
        self.db = db
        self.org_id = org_id
        self.gateway = gateway
        self.now = datetime.now(timezone.utc)
        self.config = config or {}
        self.logger = logging.getLogger(f"{__name__}.org_{org_id}")

    async def run(self) -> dict:
        """Execute the full lifecycle scan. Returns execution summary."""
        summary = {
            "agent": self.AGENT_TYPE, "organization_id": self.org_id,
            "clients_checked": 0, "milestones_found": 0,
            "refi_opportunities": 0, "referral_candidates": 0,
            "messages_queued": 0, "errors": [],
        }
        try:
            funded = self._get_funded_loans()
            summary["clients_checked"] = len(funded)
            self.logger.info("Scanning %d funded loans for org %d", len(funded), self.org_id)

            phases = [
                ("milestone", self._find_milestone_clients, self._generate_milestone_message,
                 lambda l, ln, mt: f"milestone_{mt}", "milestones_found"),
                ("refi", self._find_refi_opportunities, self._generate_refi_message,
                 lambda l, ln, s: "refi_opportunity", "refi_opportunities"),
                ("referral", self._find_referral_candidates, self._generate_referral_message,
                 lambda l, ln: "referral_request", "referral_candidates"),
            ]
            for phase, finder, gen_fn, key_fn, summary_key in phases:
                results = finder(funded)
                count, errors = self._process_phase(phase, results, gen_fn, key_fn)
                summary[summary_key] += count
                summary["messages_queued"] += count
                summary["errors"].extend(errors)

            self.db.commit()
        except Exception as e:
            self.logger.exception("Lifecycle run failed for org %d: %s", self.org_id, e)
            self.db.rollback()
            summary["errors"].append({"fatal": str(e)})

        self.logger.info(
            "Lifecycle complete org %d: %d checked, %d milestones, %d refi, %d referrals",
            self.org_id, summary["clients_checked"], summary["milestones_found"],
            summary["refi_opportunities"], summary["referral_candidates"],
        )
        return summary

    def _process_phase(self, phase: str, items: list, gen_fn, touch_key_fn) -> tuple[int, list]:
        """Process a list of phase results, generating messages and recording touches."""
        count, errors = 0, []
        for item in items:
            lead, loan = item[0], item[1]
            try:
                msg = gen_fn(*item)
                self._record_lifecycle_touch(lead, loan, touch_key_fn(*item), msg)
                count += 1
            except Exception as e:
                self.logger.exception("%s failed loan %d: %s", phase, loan.id, e)
                errors.append({"loan_id": loan.id, "phase": phase, "error": str(e)})
        return count, errors

    def _get_funded_loans(self) -> list[tuple[Lead, Loan]]:
        """Return (Lead, Loan) pairs for funded loans. Joins on borrower_email."""
        return (
            self.db.query(Lead, Loan)
            .join(Loan, and_(
                Loan.borrower_email == Lead.email,
                Loan.organization_id == Lead.organization_id,
            ))
            .filter(
                Loan.organization_id == self.org_id,
                Loan.stage.in_(FUNDED_STAGES),
                Loan.funded_date.isnot(None),
            )
            .all()
        )

    def _find_milestone_clients(self, funded: list) -> list:
        """Funded clients hitting milestone anniversaries (+/- tolerance)."""
        hits = []
        for lead, loan in funded:
            funded_dt = _ensure_utc(loan.funded_date)
            if not funded_dt:
                continue
            days = (self.now - funded_dt).days
            for m_day, m_type in self.MILESTONE_DAYS.items():
                if abs(days - m_day) <= _MILESTONE_TOLERANCE_DAYS:
                    if not self._has_existing_touch(lead.id, loan.id, f"milestone_{m_type}"):
                        hits.append((lead, loan, m_type))
                        break  # one milestone per loan per run
        return hits

    def _find_refi_opportunities(self, funded: list) -> list:
        """Funded loans where current rates are significantly lower than loan rate."""
        threshold = Decimal(str(self.config.get("refi_threshold", _DEFAULT_REFI_THRESHOLD)))
        current_rate = self._get_current_market_rate()
        if current_rate is None:
            self.logger.warning("No market rate data; skipping refi scan")
            return []

        opportunities = []
        for lead, loan in funded:
            if not loan.rate:
                continue
            rate_diff = Decimal(str(loan.rate)) - current_rate
            if rate_diff >= threshold:
                savings = self._calculate_refi_savings(loan, current_rate)
                if savings["monthly_savings"] >= Decimal("25"):
                    if not self._has_recent_touch(lead.id, loan.id, "refi_opportunity", 90):
                        opportunities.append((lead, loan, savings))
        return opportunities

    def _find_referral_candidates(self, funded: list) -> list:
        """Happy clients at optimal referral timing (90-180 days post-close)."""
        candidates = []
        for lead, loan in funded:
            funded_dt = _ensure_utc(loan.funded_date)
            if not funded_dt:
                continue
            days = (self.now - funded_dt).days
            if _REFERRAL_WINDOW[0] <= days <= _REFERRAL_WINDOW[1]:
                if self._has_negative_interactions(lead.id, loan.id):
                    continue
                if not self._has_existing_touch(lead.id, loan.id, "referral_request"):
                    candidates.append((lead, loan))
        return candidates

    def _generate_milestone_message(self, lead: Lead, loan: Loan, milestone_type: str) -> str:
        name = lead.first_name or lead.name or "there"
        template = _MILESTONE_MESSAGES.get(
            milestone_type,
            "Hi {name}, just checking in on your homeownership journey. Let us know if we can help.",
        )
        return template.format(name=name)

    def _generate_refi_message(self, lead: Lead, loan: Loan, potential_savings: dict) -> str:
        name = lead.first_name or lead.name or "there"
        s = potential_savings
        return (
            f"Hi {name}, rates have moved in your favor. Your current rate is {s['loan_rate']}%, "
            f"and today's market rate is around {s['current_market_rate']}%. "
            f"That could mean approximately ${s['monthly_savings']:,.0f}/month "
            f"(${s['annual_savings']:,.0f}/year) in savings. "
            f"Want to explore a refinance? No obligation — just a quick conversation."
        )

    def _generate_referral_message(self, lead: Lead, loan: Loan) -> str:
        name = lead.first_name or lead.name or "there"
        return (
            f"Hi {name}, we hope you're loving your home! "
            f"If you know anyone thinking about buying or refinancing, "
            f"we'd be honored if you'd pass along our name."
        )

    def _record_lifecycle_touch(self, lead: Lead, loan: Loan, touch_type: str, message: str) -> None:
        """Create Activity + Notification for the assigned LO."""
        lo_id = loan.loan_officer_id or lead.owner_id
        activity = Activity(
            organization_id=self.org_id, lead_id=lead.id, loan_id=loan.id,
            user_id=lo_id, type=ActivityType.NOTE, content=message,
            sentiment="positive",
            user_metadata={"source": self.AGENT_TYPE, "touch_type": touch_type, "automated": True},
        )
        if self.gateway:
            self.gateway.propose(
                "create_activity", lambda a=activity: self.db.add(a),
                target_entity="loan", target_id=loan.id,
                description=f"Lifecycle {touch_type} for {lead.first_name or 'client'}",
                payload={
                    "type": "note",
                    "content": message,
                    "loan_id": loan.id,
                    "lead_id": lead.id,
                    "user_id": lo_id,
                },
                notify_user_id=lo_id,
            )
        else:
            self.db.add(activity)
        if lo_id:
            borrower = lead.first_name or lead.name or "Client"
            notif = Notification(
                organization_id=self.org_id, user_id=lo_id,
                type="lifecycle_touch",
                title=f"Lifecycle: {touch_type.replace('_', ' ').title()}",
                message=f"Automated {touch_type.replace('_', ' ')} queued for {borrower} (Loan #{loan.loan_number}). Review and personalize.",
                link=f"/loans/{loan.id}", is_read=False,
            )
            if self.gateway:
                self.gateway.propose(
                    "create_notification", lambda n=notif: self.db.add(n),
                    target_entity="loan", target_id=loan.id,
                    description=f"Lifecycle touch notification for {borrower}",
                    payload={
                        "user_id": lo_id,
                        "loan_id": loan.id,
                        "lead_id": lead.id,
                        "type": "lifecycle_touch",
                        "title": f"Lifecycle: {touch_type.replace('_', ' ').title()}",
                        "message": notif.message,
                        "link": f"/loans/{loan.id}",
                    },
                    notify_user_id=lo_id,
                )
            else:
                self.db.add(notif)

    def _calculate_refi_savings(self, loan: Loan, current_market_rate: Decimal) -> dict:
        """Monthly/annual savings using standard amortization formula."""
        balance = Decimal(str(loan.amount or 0))
        loan_rate = Decimal(str(loan.rate or 0))
        term = loan.term or 360

        if loan.funded_date:
            funded_dt = _ensure_utc(loan.funded_date)
            elapsed = max(0, (self.now - funded_dt).days // 30) if funded_dt else 0
            remaining = max(1, term - elapsed)
        else:
            remaining = term

        cur_pmt = _monthly_payment(balance, loan_rate, remaining)
        new_pmt = _monthly_payment(balance, current_market_rate, remaining)
        monthly = (cur_pmt - new_pmt).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        return {
            "loan_rate": loan_rate, "current_market_rate": current_market_rate,
            "remaining_months": remaining,
            "current_payment": cur_pmt, "new_payment": new_pmt,
            "monthly_savings": monthly, "annual_savings": (monthly * 12).quantize(Decimal("0.01")),
        }

    def _get_current_market_rate(self) -> Optional[Decimal]:
        """Most recent 30yr fixed rate from RateMarketData."""
        row = (
            self.db.query(RateMarketData.rate_30yr_fixed)
            .filter(
                or_(RateMarketData.organization_id == self.org_id, RateMarketData.organization_id.is_(None)),
                RateMarketData.rate_30yr_fixed.isnot(None),
            )
            .order_by(RateMarketData.snapshot_date.desc())
            .first()
        )
        return Decimal(str(row[0])) if row and row[0] is not None else None

    def _has_existing_touch(self, lead_id: int, loan_id: int, touch_type: str) -> bool:
        return self.db.query(Activity.id).filter(
            Activity.organization_id == self.org_id,
            Activity.lead_id == lead_id, Activity.loan_id == loan_id,
            Activity.user_metadata["source"].as_string() == self.AGENT_TYPE,
            Activity.user_metadata["touch_type"].as_string() == touch_type,
        ).first() is not None

    def _has_recent_touch(self, lead_id: int, loan_id: int, touch_type: str, days: int = 90) -> bool:
        cutoff = self.now - timedelta(days=days)
        return self.db.query(Activity.id).filter(
            Activity.organization_id == self.org_id,
            Activity.lead_id == lead_id, Activity.loan_id == loan_id,
            Activity.user_metadata["source"].as_string() == self.AGENT_TYPE,
            Activity.user_metadata["touch_type"].as_string() == touch_type,
            Activity.created_at >= cutoff,
        ).first() is not None

    def _has_negative_interactions(self, lead_id: int, loan_id: int) -> bool:
        return self.db.query(Activity.id).filter(
            Activity.organization_id == self.org_id,
            or_(Activity.lead_id == lead_id, Activity.loan_id == loan_id),
            Activity.sentiment == "negative",
        ).first() is not None


def _ensure_utc(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


def _monthly_payment(principal: Decimal, annual_rate_pct: Decimal, months: int) -> Decimal:
    """Standard amortization: M = P * [r(1+r)^n] / [(1+r)^n - 1]."""
    if principal <= 0 or months <= 0:
        return Decimal("0")
    if annual_rate_pct <= 0:
        return (principal / months).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    r = annual_rate_pct / Decimal("1200")
    factor = (1 + r) ** months
    return (principal * r * factor / (factor - 1)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
