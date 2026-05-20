"""
Rate Alert Agent

Autonomous agent that monitors rate changes and alerts loan officers about
rate lock expirations, relock opportunities, and float-down candidates.
Runs on a schedule via the autonomous agent framework.

Usage:
    from services.autonomous.rate_alert_agent import RateAlertAgent

    agent = RateAlertAgent(db=session, org_id=org.id)
    summary = await agent.run()
"""

import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import and_, func
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

TERMINAL_STAGES = frozenset({
    "FUNDED", "CANCELLED", "DENIED", "DEAD",
    "WITHDRAWN", "DOES_NOT_QUALIFY", "NURTURE",
})

# Default config values
_DEFAULTS = {
    "lock_expiry_warning_days": 7,
    "rate_drop_threshold_bps": 25,      # 0.25% drop triggers float-down
    "trend_lookback_days": 14,
    "min_savings_monthly": Decimal("50"),
}


class RateAlertAgent:
    """Monitors rate changes and creates alerts for loan officers."""

    AGENT_TYPE = "rate_alert"

    def __init__(self, db: Session, org_id: int, config: dict | None = None, gateway=None):
        self.db = db
        self.org_id = org_id
        self.gateway = gateway
        self.now = datetime.now(timezone.utc)
        self.cfg = {**_DEFAULTS, **(config or {})}
        self.logger = logger

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    async def run(self) -> dict:
        """Full rate monitoring sweep. Returns summary dict."""
        expirations = self._check_rate_lock_expirations()
        relock_opps = self._identify_relock_opportunities()
        float_downs = self._find_float_down_candidates()
        trend = self._detect_rate_trends()

        alerts_created = len(expirations) + len(relock_opps) + len(float_downs)

        # Spike / drop alerts based on trend
        if trend.get("direction") == "up" and trend.get("change_bps", 0) >= 25:
            alerts_created += self._broadcast_trend_alert("rate_spike", trend)
        elif trend.get("direction") == "down" and abs(trend.get("change_bps", 0)) >= 25:
            alerts_created += self._broadcast_trend_alert("rate_drop", trend)

        try:
            self.db.flush()
        except Exception as e:
            self.logger.error("Failed to flush rate alerts: %s", e)

        return {
            "rates_analyzed": trend.get("data_points", 0),
            "alerts_created": alerts_created,
            "lock_expirations": len(expirations),
            "relock_opportunities": len(relock_opps),
            "float_down_candidates": len(float_downs),
            "trend": trend.get("direction", "stable"),
        }

    # ------------------------------------------------------------------
    # Lock expirations
    # ------------------------------------------------------------------

    def _check_rate_lock_expirations(self) -> list[dict]:
        """Find rate locks expiring within the warning window."""
        from database.models.rate_lock import RateLock
        from database.models.lead_loan import Loan, Lead
        from database.enums import RateLockStatus

        cutoff = self.now + timedelta(days=self.cfg["lock_expiry_warning_days"])

        locks = (
            self.db.query(RateLock, Loan, Lead)
            .join(Loan, RateLock.loan_id == Loan.id)
            .outerjoin(Lead, Loan.lead_id == Lead.id)
            .filter(
                RateLock.organization_id == self.org_id,
                RateLock.status == RateLockStatus.LOCKED,
                RateLock.lock_expiration_date.isnot(None),
                RateLock.lock_expiration_date <= cutoff,
                RateLock.lock_expiration_date > self.now,
                Loan.stage.notin_(TERMINAL_STAGES),
            )
            .all()
        )

        results: list[dict] = []
        for lock, loan, lead in locks:
            days_left = (lock.lock_expiration_date - self.now).days
            msg = (
                f"Rate lock expires in {days_left} day{'s' if days_left != 1 else ''} "
                f"for {loan.borrower_name} (locked at {lock.rate_locked}%). "
                f"Lock expires {lock.lock_expiration_date:%m/%d/%Y}."
            )
            self._create_rate_alert(loan, lead, "lock_expiring", msg)
            results.append({
                "loan_id": loan.id,
                "days_until_expiry": days_left,
                "locked_rate": float(lock.rate_locked) if lock.rate_locked else None,
            })
        return results

    # ------------------------------------------------------------------
    # Relock opportunities
    # ------------------------------------------------------------------

    def _identify_relock_opportunities(self) -> list[dict]:
        """Find loans where current market rate is better than locked rate."""
        from database.models.rate_lock import RateLock, RateMarketData
        from database.models.lead_loan import Loan, Lead
        from database.enums import RateLockStatus

        latest_market = (
            self.db.query(RateMarketData)
            .filter(RateMarketData.organization_id.in_([self.org_id, None]))
            .order_by(RateMarketData.snapshot_date.desc())
            .first()
        )
        if not latest_market or not latest_market.rate_30yr_fixed:
            return []

        market_rate = latest_market.rate_30yr_fixed

        locks = (
            self.db.query(RateLock, Loan, Lead)
            .join(Loan, RateLock.loan_id == Loan.id)
            .outerjoin(Lead, Loan.lead_id == Lead.id)
            .filter(
                RateLock.organization_id == self.org_id,
                RateLock.status == RateLockStatus.LOCKED,
                RateLock.rate_locked.isnot(None),
                RateLock.rate_locked > market_rate,
                Loan.stage.notin_(TERMINAL_STAGES),
            )
            .all()
        )

        results: list[dict] = []
        for lock, loan, lead in locks:
            savings = self._calculate_savings(
                loan.amount, float(lock.rate_locked), float(market_rate),
                term=loan.term or 360,
            )
            if savings["monthly_savings"] < float(self.cfg["min_savings_monthly"]):
                continue

            msg = (
                f"Relock opportunity for {loan.borrower_name}: "
                f"current lock {lock.rate_locked}% vs market {market_rate}%. "
                f"Potential savings ${savings['monthly_savings']:.0f}/mo."
            )
            self._create_rate_alert(loan, lead, "relock_opportunity", msg)
            results.append({
                "loan_id": loan.id,
                "locked_rate": float(lock.rate_locked),
                "market_rate": float(market_rate),
                **savings,
            })
        return results

    # ------------------------------------------------------------------
    # Float-down candidates
    # ------------------------------------------------------------------

    def _find_float_down_candidates(self) -> list[dict]:
        """Find locked loans eligible for float-down based on rate drops."""
        from database.models.rate_lock import RateLock, RateMarketData
        from database.models.lead_loan import Loan, Lead
        from database.enums import RateLockStatus

        latest_market = (
            self.db.query(RateMarketData)
            .filter(RateMarketData.organization_id.in_([self.org_id, None]))
            .order_by(RateMarketData.snapshot_date.desc())
            .first()
        )
        if not latest_market or not latest_market.rate_30yr_fixed:
            return []

        market_rate = latest_market.rate_30yr_fixed
        threshold_bps = self.cfg["rate_drop_threshold_bps"]

        locks = (
            self.db.query(RateLock, Loan, Lead)
            .join(Loan, RateLock.loan_id == Loan.id)
            .outerjoin(Lead, Loan.lead_id == Lead.id)
            .filter(
                RateLock.organization_id == self.org_id,
                RateLock.status == RateLockStatus.LOCKED,
                RateLock.float_down_available == True,  # noqa: E712
                RateLock.float_down_exercised == False,  # noqa: E712
                RateLock.rate_locked.isnot(None),
                Loan.stage.notin_(TERMINAL_STAGES),
            )
            .all()
        )

        results: list[dict] = []
        for lock, loan, lead in locks:
            drop_bps = (lock.rate_locked - market_rate) * 100
            if drop_bps < threshold_bps:
                continue

            savings = self._calculate_savings(
                loan.amount, float(lock.rate_locked), float(market_rate),
                term=loan.term or 360,
            )
            msg = (
                f"Float-down available for {loan.borrower_name}: "
                f"locked at {lock.rate_locked}%, market now {market_rate}% "
                f"(drop of {int(drop_bps)} bps). "
                f"Savings ${savings['monthly_savings']:.0f}/mo."
            )
            self._create_rate_alert(loan, lead, "float_down", msg)
            results.append({
                "loan_id": loan.id,
                "locked_rate": float(lock.rate_locked),
                "market_rate": float(market_rate),
                "drop_bps": int(drop_bps),
                **savings,
            })
        return results

    # ------------------------------------------------------------------
    # Trend detection
    # ------------------------------------------------------------------

    def _detect_rate_trends(self) -> dict:
        """Analyze recent rate movements and return trend summary."""
        from database.models.rate_lock import RateMarketData

        lookback = self.now.date() - timedelta(days=self.cfg["trend_lookback_days"])
        snapshots = (
            self.db.query(RateMarketData)
            .filter(
                RateMarketData.organization_id.in_([self.org_id, None]),
                RateMarketData.snapshot_date >= lookback,
                RateMarketData.rate_30yr_fixed.isnot(None),
            )
            .order_by(RateMarketData.snapshot_date.asc())
            .all()
        )

        if len(snapshots) < 2:
            return {"direction": "stable", "change_bps": 0, "data_points": len(snapshots)}

        rates = [float(s.rate_30yr_fixed) for s in snapshots]
        oldest, newest = rates[0], rates[-1]
        change_bps = round((newest - oldest) * 100)

        if change_bps > 10:
            direction = "up"
        elif change_bps < -10:
            direction = "down"
        else:
            direction = "stable"

        return {
            "direction": direction,
            "change_bps": change_bps,
            "oldest_rate": oldest,
            "newest_rate": newest,
            "data_points": len(snapshots),
            "high": max(rates),
            "low": min(rates),
        }

    # ------------------------------------------------------------------
    # Alert creation
    # ------------------------------------------------------------------

    def _create_rate_alert(
        self,
        loan: Any,
        lead: Any | None,
        alert_type: str,
        message: str,
    ) -> None:
        """Create a Notification and Activity record for the alert."""
        from database.models.security import Notification
        from database.models.communication import Activity
        from database.enums import ActivityType

        lo_id = loan.loan_officer_id
        if not lo_id:
            return

        title_map = {
            "lock_expiring": "Rate Lock Expiring Soon",
            "relock_opportunity": "Relock Opportunity Available",
            "float_down": "Float-Down Opportunity",
            "rate_spike": "Rate Spike Alert",
            "rate_drop": "Rate Drop Alert",
        }

        try:
            notif = Notification(
                user_id=lo_id,
                organization_id=self.org_id,
                type=alert_type,
                title=title_map.get(alert_type, "Rate Alert"),
                message=message,
                link=f"/pipeline/loans/{loan.id}",
                is_read=False,
            )
            act = Activity(
                organization_id=self.org_id,
                type=ActivityType.NOTE,
                content=f"[{self.AGENT_TYPE}] {message}",
                loan_id=loan.id,
                lead_id=lead.id if lead else None,
                user_id=lo_id,
            )
            if self.gateway:
                self.gateway.propose(
                    "create_notification", lambda n=notif: self.db.add(n),
                    target_entity="loan", target_id=loan.id,
                    description=title_map.get(alert_type, "Rate Alert"),
                    payload={
                        "user_id": lo_id,
                        "loan_id": loan.id,
                        "lead_id": lead.id if lead else None,
                        "type": alert_type,
                        "title": title_map.get(alert_type, "Rate Alert"),
                        "message": message,
                        "link": f"/pipeline/loans/{loan.id}",
                    },
                    notify_user_id=lo_id,
                )
                self.gateway.propose(
                    "create_activity", lambda a=act: self.db.add(a),
                    target_entity="loan", target_id=loan.id,
                    description=f"Rate alert activity for loan {loan.id}",
                    payload={
                        "type": "note",
                        "content": f"[{self.AGENT_TYPE}] {message}",
                        "loan_id": loan.id,
                        "lead_id": lead.id if lead else None,
                        "user_id": lo_id,
                    },
                    notify_user_id=lo_id,
                )
            else:
                self.db.add(notif)
                self.db.add(act)
        except Exception as e:
            self.logger.warning(
                "Failed to create rate alert for loan %s: %s", loan.id, e,
            )

    def _broadcast_trend_alert(self, alert_type: str, trend: dict) -> int:
        """Send a trend-based alert to all LOs with active pipeline loans."""
        from database.models.lead_loan import Loan
        from database.models.security import Notification

        direction = "spiked" if alert_type == "rate_spike" else "dropped"
        msg = (
            f"Rates have {direction} {abs(trend['change_bps'])} bps over the past "
            f"{self.cfg['trend_lookback_days']} days "
            f"({trend.get('oldest_rate', '?')}% -> {trend.get('newest_rate', '?')}%)."
        )
        title = "Rate Spike Alert" if alert_type == "rate_spike" else "Rate Drop Alert"

        lo_ids = (
            self.db.query(Loan.loan_officer_id)
            .filter(
                Loan.organization_id == self.org_id,
                Loan.stage.notin_(TERMINAL_STAGES),
                Loan.loan_officer_id.isnot(None),
            )
            .distinct()
            .all()
        )

        created = 0
        for (lo_id,) in lo_ids:
            try:
                self.db.add(Notification(
                    user_id=lo_id,
                    organization_id=self.org_id,
                    type=alert_type,
                    title=title,
                    message=msg,
                    link="/rate-monitor",
                    is_read=False,
                ))
                created += 1
            except Exception as e:
                self.logger.warning(
                    "Failed to create trend alert for LO %s: %s", lo_id, e,
                )
        return created

    # ------------------------------------------------------------------
    # Savings calculator
    # ------------------------------------------------------------------

    @staticmethod
    def _calculate_savings(
        loan_amount: float | Decimal,
        old_rate: float,
        new_rate: float,
        term: int = 360,
    ) -> dict:
        """Calculate monthly and total savings from a rate change.

        Args:
            loan_amount: Principal balance.
            old_rate: Current/locked annual rate as percentage (e.g. 6.5).
            new_rate: Proposed annual rate as percentage.
            term: Loan term in months (default 360 = 30yr).

        Returns:
            Dict with monthly_savings, total_savings, old_payment, new_payment.
        """
        amount = float(loan_amount) if loan_amount else 0.0
        if amount <= 0 or term <= 0:
            return {"monthly_savings": 0.0, "total_savings": 0.0,
                    "old_payment": 0.0, "new_payment": 0.0}

        def _monthly_payment(principal: float, annual_rate: float, months: int) -> float:
            if annual_rate <= 0:
                return principal / months if months else 0.0
            r = annual_rate / 100.0 / 12.0
            return principal * (r * (1 + r) ** months) / ((1 + r) ** months - 1)

        old_pmt = _monthly_payment(amount, old_rate, term)
        new_pmt = _monthly_payment(amount, new_rate, term)
        monthly = round(old_pmt - new_pmt, 2)

        return {
            "monthly_savings": monthly,
            "total_savings": round(monthly * term, 2),
            "old_payment": round(old_pmt, 2),
            "new_payment": round(new_pmt, 2),
        }
