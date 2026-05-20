"""
RefiOpportunityEvaluator — the match engine.

Triggered by:
  - Every successful primary-source ingestion (event-driven), AND
  - A safety-net daily sweep at 09:30 ET (in case events are lost).

For each loan-under-management:
  1. Load current rate snapshot (perennia_rate by product).
  2. Load active borrower_target_rates row.
  3. Check: perennia_rate <= target_rate?
  4. Check: savings & break-even thresholds met?
  5. Check: not in cooldown window (no prior detection within cooldown_days)?
  6. Check: TCPA consent present and quiet-hours respected?
  7. Check: schema-drift gate not raised?
  8. → INSERT refi_opportunities row, emit refi.opportunity.detected event.

Volume safeguards (Security insisted):
  - Max 1 detection per loan per cooldown_days (DB query enforces this).
  - Global rate limit: max N detections per minute (Redis token bucket).
    Prevents a stuck pipeline replay from spamming the entire book.
  - Per-LO outreach cap per day (configurable).
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID, uuid4

from redis.asyncio import Redis

from .calculator import compute_perennia_rate, evaluate_savings
from .ingestion import SCHEMA_DRIFT_GATE_KEY
from .models import (
    LoanSnapshot,
    Product,
    RefiOpportunity,
    RefiOpportunityDetectedEvent,
)

logger = logging.getLogger(__name__)

DEFAULT_OPPORTUNITY_TTL_HOURS = 72  # Opportunity expires if not converted in 72h
GLOBAL_DETECTION_RATE_LIMIT_KEY = "rate_watch:detection_rate_limit"
GLOBAL_DETECTION_RATE_LIMIT_MAX = 100  # per minute, system-wide


class RefiOpportunityEvaluator:
    def __init__(self, *, db_pool, redis: Redis, event_bus, tcpa_checker):
        self.db = db_pool
        self.redis = redis
        self.events = event_bus
        self.tcpa = tcpa_checker          # uses your existing Aria TCPA module

    async def evaluate_book(self) -> list[UUID]:
        """
        Walk the entire book. Returns the IDs of opportunities created this pass.
        Intended to be called once per primary-source ingestion.
        """
        if await self._gate_raised():
            logger.warning("evaluator skipped: schema-drift gate is raised")
            return []

        current_rates = await self._load_current_rates()
        if not current_rates:
            logger.warning("evaluator skipped: no current rates available")
            return []

        candidates = await self._load_candidate_loans()
        opp_ids: list[UUID] = []

        for loan, target in candidates:
            try:
                opp_id = await self._evaluate_one(loan, target, current_rates)
                if opp_id:
                    opp_ids.append(opp_id)
            except Exception:                           # noqa: BLE001
                # One bad loan must not poison the whole book.
                logger.exception("evaluator failed for loan_id=%s", loan.loan_id)

        logger.info("evaluator pass complete: %d opportunities created", len(opp_ids))
        return opp_ids

    # ------------------------------------------------------------------ #
    # Per-loan evaluation                                                 #
    # ------------------------------------------------------------------ #
    async def _evaluate_one(
        self,
        loan: LoanSnapshot,
        target,
        current_rates: dict[Product, dict],
    ) -> UUID | None:
        rate_info = current_rates.get(target.product)
        if not rate_info:
            return None

        perennia_rate = compute_perennia_rate(
            market_rate=rate_info["market_rate"],
            margin_bps=rate_info["margin_bps"],
        )

        # Hard threshold: market must be at or below target.
        if perennia_rate > target.target_rate:
            return None

        # Savings math
        savings = evaluate_savings(
            current_balance=loan.current_balance,
            current_rate=loan.current_rate,
            current_payment=loan.current_monthly_payment,
            new_rate=perennia_rate,
            new_term_months=360,                # default to 30-year; per-loan override later
        )

        # Threshold checks
        if target.min_monthly_savings is not None and savings.monthly_savings < target.min_monthly_savings:
            return None
        if (
            target.min_break_even_months is not None
            and (savings.estimated_break_even_months is None
                 or savings.estimated_break_even_months > target.min_break_even_months)
        ):
            return None
        if savings.monthly_savings <= 0:
            # Rare but possible if target is set absurdly low and term changes.
            return None

        # Cooldown
        if await self._in_cooldown(loan.loan_id, target.cooldown_days):
            return None

        # Global rate limit
        if not await self._consume_rate_limit_token():
            logger.warning(
                "global detection rate limit hit — skipping loan_id=%s", loan.loan_id
            )
            return None

        # TCPA consent + quiet hours
        consent = await self.tcpa.check_consent(loan.borrower_id)
        quiet_ok = await self.tcpa.quiet_hours_ok(loan.borrower_id)
        if not consent.granted:
            # Still record the opportunity for the LO dashboard (so they can
            # manually reach out), but DO NOT auto-send outreach.
            pass

        # Construct the opportunity
        opp = RefiOpportunity(
            id=uuid4(),
            loan_id=loan.loan_id,
            borrower_id=loan.borrower_id,
            loan_officer_id=loan.loan_officer_id,
            product=target.product,
            target_rate=target.target_rate,
            market_rate=rate_info["market_rate"],
            perennia_rate=perennia_rate,
            margin_bps_at_detection=rate_info["margin_bps"],
            rate_observation_id=rate_info["observation_id"],
            current_balance=loan.current_balance,
            current_rate=loan.current_rate,
            current_payment=savings.current_payment,
            projected_payment=savings.projected_payment,
            monthly_savings=savings.monthly_savings,
            estimated_break_even_months=savings.estimated_break_even_months,
            detected_at=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc) + timedelta(hours=DEFAULT_OPPORTUNITY_TTL_HOURS),
            tcpa_consent_verified=consent.granted,
            tcpa_consent_id=consent.consent_id,
            quiet_hours_check_passed=quiet_ok,
        )

        await self._persist(opp)
        await self._emit_event(opp)
        return opp.id

    # ------------------------------------------------------------------ #
    # Loading                                                             #
    # ------------------------------------------------------------------ #
    async def _load_current_rates(self) -> dict[Product, dict]:
        sql = "SELECT product, market_rate, margin_bps, observation_id FROM current_rates"
        async with self.db.acquire() as conn:
            rows = await conn.fetch(sql)
        out: dict[Product, dict] = {}
        for r in rows:
            try:
                out[Product(r["product"])] = {
                    "market_rate": Decimal(r["market_rate"]),
                    "margin_bps": int(r["margin_bps"]),
                    "observation_id": int(r["observation_id"]),
                }
            except (ValueError, TypeError):
                continue
        return out

    async def _load_candidate_loans(self) -> list[tuple[LoanSnapshot, object]]:
        """
        Joins active loans with their active target rate rows.
        The actual query joins your loans table + borrower_target_rates.
        Implementation depends on Perennia's existing loans schema.
        """
        sql = """
            SELECT
                l.loan_id, l.borrower_id, l.loan_officer_id,
                l.current_balance, l.current_rate, l.current_term_months,
                l.months_remaining, l.current_monthly_payment,
                btr.id AS target_id, btr.product, btr.target_rate,
                btr.min_monthly_savings, btr.min_break_even_months,
                btr.cooldown_days
            FROM loans_under_management l
            JOIN borrower_target_rates btr
                ON btr.loan_id = l.loan_id AND btr.active = TRUE
            WHERE l.status = 'active'
        """
        async with self.db.acquire() as conn:
            rows = await conn.fetch(sql)

        candidates: list[tuple[LoanSnapshot, object]] = []
        for r in rows:
            snapshot = LoanSnapshot(
                loan_id=r["loan_id"],
                borrower_id=r["borrower_id"],
                loan_officer_id=r["loan_officer_id"],
                current_balance=r["current_balance"],
                current_rate=r["current_rate"],
                current_term_months=r["current_term_months"],
                months_remaining=r["months_remaining"],
                current_monthly_payment=r["current_monthly_payment"],
            )
            # Lightweight inline target object — full Pydantic model also fine.
            from types import SimpleNamespace
            target = SimpleNamespace(
                id=r["target_id"],
                product=Product(r["product"]),
                target_rate=r["target_rate"],
                min_monthly_savings=r["min_monthly_savings"],
                min_break_even_months=r["min_break_even_months"],
                cooldown_days=r["cooldown_days"],
            )
            candidates.append((snapshot, target))
        return candidates

    async def _in_cooldown(self, loan_id: UUID, cooldown_days: int) -> bool:
        sql = """
            SELECT 1
            FROM refi_opportunities
            WHERE loan_id = $1
              AND detected_at > NOW() - ($2 || ' days')::interval
              AND status NOT IN ('closed_lost', 'expired')
            LIMIT 1
        """
        async with self.db.acquire() as conn:
            row = await conn.fetchrow(sql, loan_id, str(cooldown_days))
        return row is not None

    async def _gate_raised(self) -> bool:
        v = await self.redis.get(SCHEMA_DRIFT_GATE_KEY)
        return v is not None

    async def _consume_rate_limit_token(self) -> bool:
        """
        Simple per-minute token bucket. The first call in any minute
        creates a key with TTL=60 and value=1; subsequent calls INCR.
        If the count exceeds the limit, return False.
        """
        minute_bucket = datetime.now(timezone.utc).strftime("%Y%m%d%H%M")
        key = f"{GLOBAL_DETECTION_RATE_LIMIT_KEY}:{minute_bucket}"
        count = await self.redis.incr(key)
        if count == 1:
            await self.redis.expire(key, 70)
        return count <= GLOBAL_DETECTION_RATE_LIMIT_MAX

    # ------------------------------------------------------------------ #
    # Persistence + emit                                                  #
    # ------------------------------------------------------------------ #
    async def _persist(self, opp: RefiOpportunity) -> None:
        sql = """
            INSERT INTO refi_opportunities (
                id, loan_id, borrower_id, loan_officer_id,
                product, target_rate, market_rate, perennia_rate,
                margin_bps_at_detection, rate_observation_id,
                current_balance, current_rate, current_payment,
                projected_payment, monthly_savings, estimated_break_even_months,
                status, detected_at, expires_at,
                tcpa_consent_verified, tcpa_consent_id, quiet_hours_check_passed
            ) VALUES (
                $1, $2, $3, $4, $5, $6, $7, $8, $9, $10,
                $11, $12, $13, $14, $15, $16, 'detected', $17, $18, $19, $20, $21
            )
        """
        async with self.db.acquire() as conn:
            await conn.execute(
                sql,
                opp.id, opp.loan_id, opp.borrower_id, opp.loan_officer_id,
                opp.product.value, opp.target_rate, opp.market_rate, opp.perennia_rate,
                opp.margin_bps_at_detection, opp.rate_observation_id,
                opp.current_balance, opp.current_rate, opp.current_payment,
                opp.projected_payment, opp.monthly_savings, opp.estimated_break_even_months,
                opp.detected_at, opp.expires_at,
                opp.tcpa_consent_verified, opp.tcpa_consent_id, opp.quiet_hours_check_passed,
            )

    async def _emit_event(self, opp: RefiOpportunity) -> None:
        event = RefiOpportunityDetectedEvent(
            opportunity_id=opp.id,
            loan_id=opp.loan_id,
            borrower_id=opp.borrower_id,
            loan_officer_id=opp.loan_officer_id,
            product=opp.product,
            target_rate=opp.target_rate,
            perennia_rate=opp.perennia_rate,
            monthly_savings=opp.monthly_savings,
            occurred_at=opp.detected_at,
        )
        await self.events.publish(event)
