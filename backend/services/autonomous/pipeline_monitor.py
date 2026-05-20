"""
Pipeline Monitor Agent

Autonomous agent that monitors the loan pipeline for stalled loans,
bottlenecks, and health issues. Runs on a schedule and creates
Notification records for loan officers with stalled files.

Usage:
    from services.autonomous.pipeline_monitor import PipelineMonitorAgent

    agent = PipelineMonitorAgent(db=session, org_id=org.id)
    summary = await agent.run()
"""

import logging
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from statistics import mean, stdev
from typing import Any

from sqlalchemy.orm import Session

from database.models.communication import StageHistory
from database.models.lead_loan import Loan
from database.models.security import Notification

logger = logging.getLogger(__name__)

TERMINAL_STAGES = frozenset({
    "FUNDED", "CANCELLED", "DENIED", "DEAD",
    "WITHDRAWN", "DOES_NOT_QUALIFY", "NURTURE",
})

# Ordered pipeline stages for progress checks
ORDERED_STAGES = [
    "APPLICATION", "DISCLOSED", "PROCESSING", "SUBMITTED",
    "UNDERWRITING", "UW_RECEIVED", "CONDITIONAL_APPROVAL",
    "APPROVED", "SUSPENDED", "CTC", "CLEAR_TO_CLOSE",
    "CLOSING", "DOCS", "DOCS_OUT", "FUNDED",
]

STAGE_INDEX = {stage: idx for idx, stage in enumerate(ORDERED_STAGES)}

CLOSING_PLUS_STAGES = frozenset({
    "CLOSING", "DOCS", "DOCS_OUT", "FUNDED",
})



class PipelineMonitorAgent:
    """Scans the loan pipeline for health issues. Invoke from a scheduler."""

    AGENT_TYPE = "pipeline_monitor"

    STAGE_SLA_DAYS: dict[str, int] = {
        "APPLICATION": 5,
        "DISCLOSED": 7,
        "PROCESSING": 10,
        "SUBMITTED": 3,
        "UNDERWRITING": 7,
        "UW_RECEIVED": 3,
        "CONDITIONAL_APPROVAL": 5,
        "APPROVED": 3,
        "CTC": 3,
        "CLEAR_TO_CLOSE": 5,
        "CLOSING": 5,
        "DOCS": 3,
        "DOCS_OUT": 3,
    }

    def __init__(self, db: Session, org_id: int, config: dict | None = None, gateway=None):
        self.db = db
        self.org_id = org_id
        self.config = config or {}
        self.gateway = gateway
        self.now = datetime.now(timezone.utc)
        self.logger = logging.getLogger(f"{__name__}.org_{org_id}")

    async def run(self) -> dict[str, Any]:
        """Execute a full pipeline health check and return a summary."""
        self.logger.info("Pipeline monitor starting for org %s", self.org_id)
        _base = {"agent": self.AGENT_TYPE, "organization_id": self.org_id}

        try:
            active_loans = self._get_active_loans()
            if not active_loans:
                self.logger.info("No active loans for org %s", self.org_id)
                return {**_base, "loans_checked": 0, "stalled_count": 0,
                        "bottleneck_stages": [], "health_score": 100,
                        "health_breakdown": {}, "closing_at_risk": [],
                        "notifications_sent": 0, "per_lo_summary": []}

            stalled = self._find_stalled_loans(active_loans)
            bottlenecks = self._detect_bottlenecks(active_loans)
            closing_at_risk = self._check_closing_deadlines(active_loans)
            health = self._calculate_pipeline_health_score(active_loans, stalled, bottlenecks)
            per_lo = self._generate_lo_summaries(active_loans, stalled)
            notifs = self._notify_stalled_loans(stalled)

            summary = {
                **_base,
                "loans_checked": len(active_loans),
                "stalled_count": len(stalled),
                "bottleneck_stages": list(bottlenecks.keys()),
                "health_score": health["score"],
                "health_breakdown": health["breakdown"],
                "closing_at_risk": [
                    {"loan_id": l.id, "loan_number": l.loan_number,
                     "stage": l.stage,
                     "closing_date": l.closing_date.isoformat() if l.closing_date else None}
                    for l in closing_at_risk
                ],
                "notifications_sent": notifs,
                "per_lo_summary": per_lo,
            }
            self.logger.info(
                "Pipeline monitor complete: %d loans, %d stalled, score=%d",
                len(active_loans), len(stalled), health["score"],
            )
            return summary

        except Exception as e:
            self.logger.exception("Pipeline monitor failed for org %s: %s", self.org_id, e)
            return {**_base, "error": str(e), "loans_checked": 0,
                    "stalled_count": 0, "bottleneck_stages": [],
                    "health_score": 0, "notifications_sent": 0,
                    "per_lo_summary": []}

    def _get_active_loans(self) -> list[Loan]:
        """Fetch all non-terminal loans for this organization."""
        return (
            self.db.query(Loan)
            .filter(
                Loan.organization_id == self.org_id,
                ~Loan.stage.in_(TERMINAL_STAGES),
            )
            .all()
        )

    def _get_stage_duration(self, loan: Loan) -> int:
        """Days in current stage (StageHistory -> stage_changed_at -> updated_at fallback)."""
        last_change = (
            self.db.query(StageHistory.changed_at)
            .filter(StageHistory.loan_id == loan.id, StageHistory.organization_id == self.org_id)
            .order_by(StageHistory.changed_at.desc())
            .first()
        )
        entered_at = (
            (last_change[0] if last_change and last_change[0] else None)
            or loan.stage_changed_at or loan.updated_at or loan.created_at
        )
        if entered_at is None:
            return 0
        if entered_at.tzinfo is None:
            entered_at = entered_at.replace(tzinfo=timezone.utc)
        return max(int((self.now - entered_at).total_seconds() / 86400), 0)

    def _find_stalled_loans(self, active_loans: list[Loan]) -> list[dict[str, Any]]:
        """Identify loans that have exceeded the SLA for their current stage."""
        stalled: list[dict[str, Any]] = []

        for loan in active_loans:
            stage = (loan.stage or "").upper()
            sla_days = self.STAGE_SLA_DAYS.get(stage)
            if sla_days is None:
                continue

            days_in_stage = self._get_stage_duration(loan)
            if days_in_stage > sla_days:
                stalled.append({
                    "loan_id": loan.id,
                    "loan_number": loan.loan_number,
                    "borrower_name": loan.borrower_name,
                    "stage": stage,
                    "days_in_stage": days_in_stage,
                    "sla_days": sla_days,
                    "overdue_by": days_in_stage - sla_days,
                    "loan_officer_id": loan.loan_officer_id,
                    "amount": float(loan.amount) if loan.amount else 0,
                })

        # Sort by overdue severity (worst first)
        stalled.sort(key=lambda x: x["overdue_by"], reverse=True)
        return stalled

    def _detect_bottlenecks(self, active_loans: list[Loan]) -> dict[str, Any]:
        """Flag stages where loan count exceeds mean + 1.5 std dev."""
        stage_counts: dict[str, int] = defaultdict(int)
        for loan in active_loans:
            stage = (loan.stage or "").upper()
            if stage in STAGE_INDEX:
                stage_counts[stage] += 1
        if not stage_counts:
            return {}

        counts = list(stage_counts.values())
        avg = mean(counts)
        threshold = (avg + 1.5 * stdev(counts)) if len(counts) >= 3 else max(avg * 2, 5)

        bottlenecks: dict[str, Any] = {}
        for stage, count in stage_counts.items():
            if count > threshold:
                stage_loans = [l for l in active_loans if (l.stage or "").upper() == stage]
                avg_days = round(mean(self._get_stage_duration(l) for l in stage_loans), 1) if stage_loans else 0.0
                bottlenecks[stage] = {"count": count, "threshold": round(threshold, 1), "avg_days_in_stage": avg_days}
        return bottlenecks

    def _check_closing_deadlines(self, active_loans: list[Loan]) -> list[Loan]:
        """Loans with closing date in next 14 days not yet at CLOSING+ stage."""
        horizon = self.now + timedelta(days=14)
        at_risk = []
        for loan in active_loans:
            if not loan.closing_date:
                continue
            cdt = loan.closing_date
            if cdt.tzinfo is None:
                cdt = cdt.replace(tzinfo=timezone.utc)
            if self.now < cdt <= horizon and (loan.stage or "").upper() not in CLOSING_PLUS_STAGES:
                at_risk.append(loan)
        at_risk.sort(key=lambda l: l.closing_date)
        return at_risk

    def _calculate_pipeline_health_score(
        self, active_loans: list[Loan], stalled_loans: list[dict],
        bottlenecks: dict[str, Any],
    ) -> dict[str, Any]:
        """Composite 0-100 health score: on-track(40) + velocity(20) + closing(20) + distribution(20)."""
        total = len(active_loans)

        # On-track (40 pts): % of loans within SLA
        stalled_ids = {s["loan_id"] for s in stalled_loans}
        on_track_pct = (total - len(stalled_ids)) / total if total else 1.0
        on_track_score = round(on_track_pct * 40, 1)

        # Velocity (20 pts): avg days-in-stage / SLA ratio
        ratios = []
        for loan in active_loans:
            sla = self.STAGE_SLA_DAYS.get((loan.stage or "").upper())
            if sla:
                ratios.append(self._get_stage_duration(loan) / sla)
        if ratios:
            velocity_score = round(max(0, min(20, 20 * (1 - (mean(ratios) - 1) / 2))), 1)
        else:
            velocity_score = 20.0

        # Closing reliability (20 pts): % of loans whose closing date looks achievable
        with_closing = [l for l in active_loans if l.closing_date]
        if with_closing:
            funded_idx = STAGE_INDEX.get("FUNDED", len(ORDERED_STAGES) - 1)
            achievable = 0
            for loan in with_closing:
                cdt = loan.closing_date
                if cdt.tzinfo is None:
                    cdt = cdt.replace(tzinfo=timezone.utc)
                stages_left = funded_idx - STAGE_INDEX.get((loan.stage or "").upper(), 0)
                days_left = (cdt - self.now).days
                if days_left >= stages_left * 2:
                    achievable += 1
            closing_score = round((achievable / len(with_closing)) * 20, 1)
        else:
            closing_score = 20.0

        # Distribution (20 pts): evenness via coefficient of variation
        counts = [
            sum(1 for l in active_loans if (l.stage or "").upper() == s)
            for s in ORDERED_STAGES if s not in TERMINAL_STAGES
        ]
        counts = [c for c in counts if c > 0]
        if len(counts) >= 2:
            cv = stdev(counts) / mean(counts) if mean(counts) > 0 else 0
            distribution_score = round(max(0, min(20, 20 * (1 - cv))), 1)
        else:
            distribution_score = 20.0

        score = max(0, min(100, int(on_track_score + velocity_score + closing_score + distribution_score)))
        return {"score": score, "breakdown": {
            "on_track": on_track_score, "velocity": velocity_score,
            "closing_reliability": closing_score, "distribution": distribution_score,
        }}

    def _generate_lo_summaries(
        self, active_loans: list[Loan], stalled_loans: list[dict],
    ) -> list[dict[str, Any]]:
        """Per-loan-officer pipeline summary."""
        lo_loans: dict[int | None, list[Loan]] = defaultdict(list)
        for loan in active_loans:
            lo_loans[loan.loan_officer_id].append(loan)

        stalled_by_lo: dict[int | None, int] = defaultdict(int)
        volume_by_lo: dict[int | None, float] = defaultdict(float)
        for s in stalled_loans:
            stalled_by_lo[s["loan_officer_id"]] += 1
            volume_by_lo[s["loan_officer_id"]] += s["amount"]

        summaries = []
        for lo_id, loans in lo_loans.items():
            stage_bkdn: dict[str, int] = defaultdict(int)
            for loan in loans:
                stage_bkdn[(loan.stage or "UNKNOWN").upper()] += 1
            summaries.append({
                "loan_officer_id": lo_id,
                "active_loans": len(loans),
                "total_volume": round(sum(float(l.amount) for l in loans if l.amount), 2),
                "stalled_count": stalled_by_lo.get(lo_id, 0),
                "stalled_volume": round(volume_by_lo.get(lo_id, 0), 2),
                "stage_breakdown": dict(stage_bkdn),
            })
        summaries.sort(key=lambda x: x["stalled_count"], reverse=True)
        return summaries

    def _notify_stalled_loans(self, stalled_loans: list[dict]) -> int:
        """Create one Notification per LO with stalled loans (deduped per day)."""
        if not stalled_loans:
            return 0

        by_lo: dict[int, list[dict]] = defaultdict(list)
        for s in stalled_loans:
            if s.get("loan_officer_id"):
                by_lo[s["loan_officer_id"]].append(s)

        today_start = self.now.replace(hour=0, minute=0, second=0, microsecond=0)
        created = 0
        for lo_id, loans in by_lo.items():
            try:
                # Skip if already notified today
                if self.db.query(Notification.id).filter(
                    Notification.user_id == lo_id,
                    Notification.organization_id == self.org_id,
                    Notification.type == "pipeline_stalled",
                    Notification.is_read == False,  # noqa: E712
                    Notification.created_at >= today_start,
                ).first():
                    continue

                w = loans[0]  # worst offender (sorted by overdue_by desc)
                if len(loans) == 1:
                    title = f"Stalled loan: {w['borrower_name']}"
                    msg = f"{w['borrower_name']} in {w['stage']} for {w['days_in_stage']}d (SLA: {w['sla_days']}d)."
                else:
                    title = f"{len(loans)} stalled loans need attention"
                    msg = (f"{len(loans)} loans exceeding SLAs. Worst: {w['borrower_name']} "
                           f"in {w['stage']} for {w['days_in_stage']}d (SLA: {w['sla_days']}d).")

                notif = Notification(
                    user_id=lo_id, organization_id=self.org_id,
                    type="pipeline_stalled", title=title, message=msg,
                    link="/pipeline?filter=stalled", is_read=False,
                )
                if self.gateway:
                    self.gateway.propose(
                        "create_notification",
                        lambda n=notif: self.db.add(n),
                        target_entity="loan",
                        target_id=w.get("loan_id"),
                        description=title,
                    )
                else:
                    self.db.add(notif)
                created += 1
            except Exception as e:
                self.logger.warning("Failed to create notification for LO %s: %s", lo_id, e)

        if created:
            try:
                self.db.flush()
            except Exception as e:
                self.logger.error("Failed to flush notifications: %s", e)
                created = 0
        return created
