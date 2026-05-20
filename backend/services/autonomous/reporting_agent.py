"""
Reporting Agent

Autonomous agent that generates daily/weekly reports and morning briefings
for loan officers. Calculates pipeline metrics, conversion funnels, velocity,
and creates actionable summaries persisted to the MorningBriefing table.

Usage:
    from services.autonomous.reporting_agent import ReportingAgent

    agent = ReportingAgent(db=session, org_id=org.id)
    summary = await agent.run()
"""

import logging
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import and_, func
from sqlalchemy.orm import Session

from database.models.communication import Activity, StageHistory
from database.models.core import User
from database.models.lead_loan import Lead, Loan
from database.models.morning_briefing import MorningBriefing
from database.models.security import Notification

logger = logging.getLogger(__name__)

TERMINAL_STAGES = frozenset({
    "FUNDED", "CANCELLED", "DENIED", "DEAD",
    "WITHDRAWN", "DOES_NOT_QUALIFY", "NURTURE",
})
ORDERED_STAGES = [
    "APPLICATION", "DISCLOSED", "PROCESSING", "SUBMITTED",
    "UNDERWRITING", "UW_RECEIVED", "CONDITIONAL_APPROVAL",
    "APPROVED", "SUSPENDED", "CTC", "CLEAR_TO_CLOSE",
    "CLOSING", "DOCS", "DOCS_OUT", "FUNDED",
]
STAGE_INDEX = {s: i for i, s in enumerate(ORDERED_STAGES)}
SLA_DAYS = {
    "APPLICATION": 5, "DISCLOSED": 7, "PROCESSING": 10, "SUBMITTED": 3,
    "UNDERWRITING": 7, "UW_RECEIVED": 3, "CONDITIONAL_APPROVAL": 5,
    "APPROVED": 3, "CTC": 3, "CLEAR_TO_CLOSE": 5, "CLOSING": 5,
    "DOCS": 3, "DOCS_OUT": 3,
}


class ReportingAgent:
    """Generates daily briefings and pipeline reports for every active LO."""

    AGENT_TYPE = "reporting"

    def __init__(self, db: Session, org_id: int, config: dict | None = None, gateway=None):
        self.db = db
        self.org_id = org_id
        self.config = config or {}
        self.gateway = gateway
        self.now = datetime.now(timezone.utc)
        self.today = self.now.date()
        self.logger = logging.getLogger(f"{__name__}.org_{org_id}")

    async def run(self) -> dict:
        """Generate morning briefings for all active LOs and return a summary."""
        self.logger.info("Reporting agent starting for org %s", self.org_id)
        _base: dict[str, Any] = {"agent": self.AGENT_TYPE, "organization_id": self.org_id}
        try:
            los = self._get_active_los()
            if not los:
                self.logger.info("No active LOs for org %s", self.org_id)
                return {**_base, "briefings_generated": 0, "los_covered": 0,
                        "avg_pipeline_volume": 0.0, "org_highlights": []}
            generated = 0
            total_vol = 0.0
            org_hl: list[str] = []
            for lo in los:
                try:
                    b = self._generate_daily_briefing(lo.id)
                    self._save_morning_briefing(lo.id, b)
                    self._create_notification(lo.id)
                    generated += 1
                    total_vol += b.get("pipeline_volume", 0.0)
                    org_hl.extend(b.get("highlights", [])[:2])
                except Exception as e:
                    self.logger.exception("Briefing failed for LO %s: %s", lo.id, e)
            avg_vol = total_vol / len(los) if los else 0.0
            self.logger.info("Reporting agent complete: %d briefings for %d LOs", generated, len(los))
            return {**_base, "briefings_generated": generated, "los_covered": len(los),
                    "avg_pipeline_volume": round(avg_vol, 2), "org_highlights": org_hl[:10]}
        except Exception as e:
            self.logger.exception("Reporting agent failed for org %s: %s", self.org_id, e)
            return {**_base, "error": str(e), "briefings_generated": 0,
                    "los_covered": 0, "avg_pipeline_volume": 0.0, "org_highlights": []}

    # -- Daily briefing --------------------------------------------------------

    def _generate_daily_briefing(self, user_id: int) -> dict:
        """Build a complete morning briefing for one loan officer."""
        pipeline = self._calculate_pipeline_metrics(user_id=user_id)
        return {
            "user_id": user_id,
            "briefing_date": self.today.isoformat(),
            "pipeline": pipeline,
            "conversion": self._calculate_conversion_metrics(),
            "velocity": self._calculate_velocity_metrics(),
            "highlights": self._identify_highlights(user_id),
            "action_items": self._generate_action_items(user_id),
            "yesterday_activity": self._yesterday_activity(user_id),
            "week_over_week": self._week_over_week_trends(user_id),
            "pipeline_volume": pipeline.get("total_volume", 0.0),
        }

    # -- Pipeline metrics ------------------------------------------------------

    def _calculate_pipeline_metrics(self, user_id: int | None = None) -> dict:
        """Pipeline snapshot: active loan count and volume by stage."""
        q = self.db.query(Loan).filter(
            Loan.organization_id == self.org_id, ~Loan.stage.in_(TERMINAL_STAGES))
        if user_id is not None:
            q = q.filter(Loan.loan_officer_id == user_id)
        loans = q.all()
        by_stage: dict[str, dict] = defaultdict(lambda: {"count": 0, "volume": 0.0})
        total_vol = 0.0
        for loan in loans:
            stage = (loan.stage or "").upper()
            amt = float(loan.amount) if loan.amount else 0.0
            by_stage[stage]["count"] += 1
            by_stage[stage]["volume"] += amt
            total_vol += amt
        week_end = self.now + timedelta(days=7)
        closings_week = sum(
            1 for l in loans
            if l.closing_date and self.now <= self._tz(l.closing_date) <= week_end)
        return {
            "active_count": len(loans), "total_volume": round(total_vol, 2),
            "by_stage": dict(sorted(by_stage.items(), key=lambda x: STAGE_INDEX.get(x[0], 99))),
            "closings_this_week": closings_week,
        }

    # -- Conversion metrics ----------------------------------------------------

    def _calculate_conversion_metrics(self, days: int = 30) -> dict:
        """Lead-to-funded conversion rates over the given window."""
        cutoff = self.now - timedelta(days=days)
        total_leads = self.db.query(func.count(Lead.id)).filter(
            Lead.organization_id == self.org_id, Lead.created_at >= cutoff).scalar() or 0
        app_leads = self.db.query(func.count(Lead.id)).filter(
            Lead.organization_id == self.org_id, Lead.created_at >= cutoff,
            Lead.stage.in_(["Application", "APPLICATION"])).scalar() or 0
        funded = self.db.query(func.count(Loan.id)).filter(
            Loan.organization_id == self.org_id, Loan.funded_date >= cutoff,
            Loan.stage == "FUNDED").scalar() or 0
        total_apps = self.db.query(func.count(Loan.id)).filter(
            Loan.organization_id == self.org_id, Loan.created_at >= cutoff).scalar() or 0
        sources = self.db.query(Lead.source, func.count(Lead.id).label("cnt")).filter(
            Lead.organization_id == self.org_id, Lead.created_at >= cutoff,
            Lead.source.isnot(None)).group_by(Lead.source).order_by(
            func.count(Lead.id).desc()).limit(5).all()
        safe_div = lambda n, d: round(n / d * 100, 1) if d else 0.0
        return {
            "period_days": days, "total_leads": total_leads,
            "lead_to_app_rate": safe_div(app_leads, total_leads),
            "app_to_funded_rate": safe_div(funded, total_apps),
            "pull_through_rate": safe_div(funded, total_leads),
            "funded_count": funded,
            "top_sources": [{"source": s.source, "count": s.cnt} for s in sources],
        }

    # -- Velocity metrics ------------------------------------------------------

    def _calculate_velocity_metrics(self, days: int = 30) -> dict:
        """Average days spent in each pipeline stage over the window."""
        cutoff = self.now - timedelta(days=days)
        transitions = self.db.query(StageHistory).filter(
            StageHistory.organization_id == self.org_id,
            StageHistory.entity_type == "loan",
            StageHistory.changed_at >= cutoff,
            StageHistory.duration_in_previous_stage.isnot(None)).all()
        durations: dict[str, list[int]] = defaultdict(list)
        for t in transitions:
            stage = (t.from_stage or "").upper()
            if stage in STAGE_INDEX:
                durations[stage].append(t.duration_in_previous_stage)
        avg_days = {}
        for s in ORDERED_STAGES:
            if durations.get(s):
                avg_days[s] = round(sum(durations[s]) / len(durations[s]), 1)
        total_avg = round(sum(avg_days.values()) / len(avg_days), 1) if avg_days else 0.0
        return {"period_days": days, "avg_days_by_stage": avg_days, "avg_total_cycle_days": total_avg}

    # -- Highlights ------------------------------------------------------------

    def _identify_highlights(self, user_id: int) -> list[str]:
        """Notable events: new loans, recent closings, milestones."""
        hl: list[str] = []
        since = self.now - timedelta(days=1)
        _fmt = lambda l: f"${float(l.amount):,.0f}" if l.amount else "N/A"
        # Recently funded
        for loan in self.db.query(Loan).filter(
                Loan.organization_id == self.org_id, Loan.loan_officer_id == user_id,
                Loan.stage == "FUNDED", Loan.funded_date >= since).all():
            hl.append(f"Loan {loan.loan_number} funded ({_fmt(loan)}) - {loan.borrower_name}")
        # New pipeline loans
        for loan in self.db.query(Loan).filter(
                Loan.organization_id == self.org_id, Loan.loan_officer_id == user_id,
                Loan.created_at >= since).all():
            if loan.stage != "FUNDED":
                hl.append(f"New loan: {loan.borrower_name} ({_fmt(loan)}, {loan.loan_type or 'N/A'})")
        # CTC milestones
        for t in self.db.query(StageHistory).filter(
                StageHistory.organization_id == self.org_id,
                StageHistory.entity_type == "loan",
                StageHistory.to_stage.in_(["CTC", "CLEAR_TO_CLOSE"]),
                StageHistory.changed_at >= since).join(
                Loan, and_(StageHistory.loan_id == Loan.id,
                           Loan.loan_officer_id == user_id)).all():
            hl.append(f"Loan cleared to close (stage: {t.to_stage})")
        return hl[:10]

    # -- Action items ----------------------------------------------------------

    def _generate_action_items(self, user_id: int) -> list[dict]:
        """Tasks needing attention: stalled loans, upcoming closings, expiring locks."""
        items: list[dict] = []
        loans = self.db.query(Loan).filter(
            Loan.organization_id == self.org_id, Loan.loan_officer_id == user_id,
            ~Loan.stage.in_(TERMINAL_STAGES)).all()
        close_horizon = self.now + timedelta(days=3)
        lock_horizon = self.now + timedelta(days=7)
        for loan in loans:
            # Closings in next 3 days
            if loan.closing_date:
                cd = self._tz(loan.closing_date)
                if self.now <= cd <= close_horizon:
                    items.append({"type": "closing_soon", "priority": "high",
                        "loan_id": loan.id, "loan_number": loan.loan_number,
                        "message": f"Closing in {(cd - self.now).days}d: {loan.borrower_name} ({loan.loan_number})"})
            # Stalled beyond SLA
            stage = (loan.stage or "").upper()
            sla = SLA_DAYS.get(stage)
            if sla:
                days_in = self._days_in_stage(loan)
                if days_in > sla:
                    items.append({"type": "stalled_loan", "priority": "medium",
                        "loan_id": loan.id, "loan_number": loan.loan_number,
                        "message": f"Stalled {days_in}d in {stage} (SLA: {sla}d): {loan.borrower_name}"})
            # Expiring rate locks
            if loan.lock_expiration_date:
                exp = self._tz(loan.lock_expiration_date)
                if self.now <= exp <= lock_horizon:
                    items.append({"type": "lock_expiring", "priority": "high",
                        "loan_id": loan.id, "loan_number": loan.loan_number,
                        "message": f"Rate lock expires in {(exp - self.now).days}d: {loan.borrower_name}"})
        pri = {"high": 0, "medium": 1, "low": 2}
        items.sort(key=lambda x: pri.get(x.get("priority", "low"), 2))
        return items[:15]

    # -- Yesterday's activity --------------------------------------------------

    def _yesterday_activity(self, user_id: int) -> dict:
        """New leads, stage changes, and communications from the last 24h."""
        since = self.now - timedelta(days=1)
        new_leads = self.db.query(func.count(Lead.id)).filter(
            Lead.organization_id == self.org_id, Lead.owner_id == user_id,
            Lead.created_at >= since).scalar() or 0
        stage_changes = self.db.query(func.count(StageHistory.id)).filter(
            StageHistory.organization_id == self.org_id,
            StageHistory.changed_at >= since).join(
            Loan, and_(StageHistory.loan_id == Loan.id,
                       Loan.loan_officer_id == user_id)).scalar() or 0
        acts = self.db.query(Activity.type, func.count(Activity.id)).filter(
            Activity.organization_id == self.org_id, Activity.user_id == user_id,
            Activity.created_at >= since).group_by(Activity.type).all()
        by_type = {str(a.type): a[1] for a in acts}
        return {"new_leads": new_leads, "stage_changes": stage_changes,
                "activities_by_type": by_type, "total_activities": sum(by_type.values())}

    # -- Week-over-week trends -------------------------------------------------

    def _week_over_week_trends(self, user_id: int) -> dict:
        """Compare this week vs last week: lead count, funded volume."""
        tw_start = self.now - timedelta(days=7)
        lw_start = self.now - timedelta(days=14)

        def _leads(start: datetime, end: datetime) -> int:
            return self.db.query(func.count(Lead.id)).filter(
                Lead.organization_id == self.org_id, Lead.owner_id == user_id,
                Lead.created_at >= start, Lead.created_at < end).scalar() or 0

        def _vol(start: datetime, end: datetime) -> float:
            r = self.db.query(func.sum(Loan.amount)).filter(
                Loan.organization_id == self.org_id, Loan.loan_officer_id == user_id,
                Loan.stage == "FUNDED", Loan.funded_date >= start,
                Loan.funded_date < end).scalar()
            return float(r) if r else 0.0

        def _pct(cur: float, prev: float) -> float:
            return (100.0 if cur > 0 else 0.0) if prev == 0 else round((cur - prev) / prev * 100, 1)

        tw_l, lw_l = _leads(tw_start, self.now), _leads(lw_start, tw_start)
        tw_v, lw_v = _vol(tw_start, self.now), _vol(lw_start, tw_start)
        return {"leads_this_week": tw_l, "leads_last_week": lw_l,
                "leads_change_pct": _pct(tw_l, lw_l),
                "funded_volume_this_week": round(tw_v, 2),
                "funded_volume_last_week": round(lw_v, 2),
                "volume_change_pct": _pct(tw_v, lw_v)}

    # -- Persistence -----------------------------------------------------------

    def _save_morning_briefing(self, user_id: int, briefing_data: dict) -> None:
        """Persist briefing to MorningBriefing table (upsert per user+date)."""
        existing = self.db.query(MorningBriefing).filter(
            MorningBriefing.user_id == user_id,
            MorningBriefing.briefing_date == self.today).first()
        narrative = self._build_narrative(briefing_data)
        if existing:
            existing.briefing_data = briefing_data
            existing.status = "delivered"
            existing.ai_narrative = narrative
        else:
            self.db.add(MorningBriefing(
                user_id=user_id, organization_id=self.org_id,
                briefing_date=self.today, briefing_level="individual",
                status="delivered", briefing_data=briefing_data,
                ai_narrative=narrative))
        self.db.flush()

    def _create_notification(self, user_id: int) -> None:
        """Create a notification linking the LO to their morning briefing."""
        notif = Notification(
            user_id=user_id, organization_id=self.org_id,
            type="morning_briefing", title="Morning Briefing Ready",
            message=f"Your briefing for {self.today.strftime('%B %d, %Y')} is ready.",
            link="/dashboard/briefing", is_read=False)
        if self.gateway:
            self.gateway.propose(
                "create_notification", lambda n=notif: (self.db.add(n), self.db.flush()),
                target_entity="user", target_id=user_id,
                description="Morning briefing notification",
                payload={
                    "user_id": user_id,
                    "type": "morning_briefing",
                    "title": "Morning Briefing Ready",
                    "message": notif.message,
                    "link": "/dashboard/briefing",
                },
                notify_user_id=user_id,
            )
        else:
            self.db.add(notif)
            self.db.flush()

    # -- Active LOs ------------------------------------------------------------

    def _get_active_los(self) -> list[User]:
        """Return active loan officers in this organization."""
        return self.db.query(User).filter(
            User.organization_id == self.org_id,
            User.is_active.is_(True),
            User.role.in_(["loan_officer", "admin"])).all()

    # -- Helpers ---------------------------------------------------------------

    def _tz(self, dt: datetime) -> datetime:
        """Ensure a datetime is timezone-aware (default UTC)."""
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)

    def _days_in_stage(self, loan: Loan) -> int:
        """Days the loan has been in its current stage."""
        last = self.db.query(StageHistory.changed_at).filter(
            StageHistory.loan_id == loan.id,
            StageHistory.organization_id == self.org_id).order_by(
            StageHistory.changed_at.desc()).first()
        entered = (last[0] if last and last[0] else None) or loan.stage_changed_at or loan.updated_at or loan.created_at
        if not entered:
            return 0
        return max(int((self.now - self._tz(entered)).total_seconds() / 86400), 0)

    def _build_narrative(self, briefing: dict) -> str:
        """Short narrative summary for the MorningBriefing.ai_narrative field."""
        p = briefing.get("pipeline", {})
        parts = [f"You have {p.get('active_count', 0)} active loans totaling ${p.get('total_volume', 0):,.0f}."]
        if c := p.get("closings_this_week"):
            parts.append(f"{c} closing(s) this week.")
        if hl := briefing.get("highlights", []):
            parts.append(f"Highlights: {'; '.join(hl[:3])}.")
        if items := briefing.get("action_items", []):
            hp = sum(1 for a in items if a.get("priority") == "high")
            parts.append(f"{len(items)} action item(s), {hp} high-priority.")
        return " ".join(parts)
