"""
MUM Valuation Routes — Batch recalculation endpoint for MUM client
property values, equity, LTV, maturity dates, and refi scores.

Admin-only endpoint that triggers full recalc of computed fields.
"""

import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from db import get_db
from agents.utils.financial_calcs import (
    calculate_remaining_balance,
    estimate_current_property_value,
    get_appreciation_rate,
    calculate_monthly_payment,
    calculate_rate_savings,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/mum/batch", tags=["mum-valuation"])

# --- Startup migration: ensure new columns exist on mum_clients ----------
try:
    from db import engine as _engine
    with _engine.connect() as _conn:
        _conn.execute(text("""
            ALTER TABLE mum_clients ADD COLUMN IF NOT EXISTS term INTEGER DEFAULT 360;
            ALTER TABLE mum_clients ADD COLUMN IF NOT EXISTS maturity_date TIMESTAMP;
            ALTER TABLE mum_clients ADD COLUMN IF NOT EXISTS estimated_equity FLOAT;
            ALTER TABLE mum_clients ADD COLUMN IF NOT EXISTS current_ltv FLOAT;
            ALTER TABLE mum_clients ADD COLUMN IF NOT EXISTS refi_score INTEGER DEFAULT 0;
            ALTER TABLE mum_clients ADD COLUMN IF NOT EXISTS property_state VARCHAR;
            ALTER TABLE mum_clients ADD COLUMN IF NOT EXISTS property_zip VARCHAR;
        """))
        _conn.commit()
    logger.info("mum_clients: ensured 7 valuation columns exist")
except Exception as _e:
    logger.warning(f"mum_clients column migration skipped: {_e}")
# -------------------------------------------------------------------------

DEFAULT_MARKET_RATE = 6.5
DEFAULT_CLOSING_COST_PCT = 0.02


def _get_market_rate(db: Session) -> float:
    try:
        row = db.execute(text("SELECT value FROM settings WHERE key = 'current_market_rate' LIMIT 1")).fetchone()
        if row and row[0]:
            return float(row[0])
    except Exception as e:
        logger.error(f"Error in _get_market_rate: {e}")
    return DEFAULT_MARKET_RATE


@router.post("/recalculate")
async def batch_recalculate(
    dry_run: bool = False,
    limit: int = 1000,
    db: Session = Depends(get_db),
    current_user=Depends(lambda: None),  # Will be replaced by actual auth
):
    """
    Batch recalculate all MUM client computed fields:
    - current_property_value (compound appreciation)
    - estimated_equity (value - amortized balance)
    - current_ltv (balance / value)
    - maturity_date (first_payment + term)
    - refi_score (0-100)
    - refinance_opportunity (boolean)
    - estimated_savings (annual)
    """
    # Auth check — require platform admin or site admin
    try:
        from auth.dependencies import get_current_user
        current_user = await get_current_user(request, db)
        if not getattr(current_user, 'is_admin', False):
            raise HTTPException(status_code=403, detail="Admin access required")
    except ImportError:
        pass  # Allow in dev without auth

    market_rate = _get_market_rate(db)

    rows = db.execute(text("""
        SELECT id, appraisal_value_at_closing, original_loan_amount,
               interest_rate, original_rate, term, first_payment_date,
               original_close_date, property_state
        FROM mum_clients
        WHERE status = 'Active'
        ORDER BY id
        LIMIT :lim
    """), {"lim": limit}).fetchall()

    if not rows:
        return {"message": "No active MUM clients found", "updated": 0}

    updated = 0
    errors = 0

    for row in rows:
        try:
            original_value = float(row.appraisal_value_at_closing or 0)
            original_amount = float(row.original_loan_amount or 0)
            rate = float(row.interest_rate or row.original_rate or 6.5) / 100
            term = row.term or 360
            state = row.property_state

            first_pmt = row.first_payment_date or row.original_close_date
            if first_pmt:
                if hasattr(first_pmt, 'tzinfo') and first_pmt.tzinfo is None:
                    first_pmt = first_pmt.replace(tzinfo=timezone.utc)
                months_passed = max(0, (datetime.now(timezone.utc) - first_pmt).days // 30)
            else:
                months_passed = 0

            # Property value
            appreciation_rate = get_appreciation_rate(state)
            current_value = estimate_current_property_value(original_value, months_passed, appreciation_rate)

            # Balance
            remaining_balance = calculate_remaining_balance(original_amount, rate, term, months_passed)

            # Equity / LTV
            equity = current_value - remaining_balance
            ltv = (remaining_balance / current_value * 100) if current_value > 0 else 0

            # Maturity
            maturity = None
            if first_pmt:
                maturity = first_pmt + timedelta(days=term * 30.44)

            # Refi score (simplified inline version of the full scoring)
            current_rate_pct = rate * 100
            rate_diff = current_rate_pct - market_rate
            equity_pct = 100 - ltv
            score = 0

            # Rate differential (0-35)
            if rate_diff >= 2.0: score += 35
            elif rate_diff >= 1.5: score += 30
            elif rate_diff >= 1.0: score += 25
            elif rate_diff >= 0.75: score += 20
            elif rate_diff >= 0.5: score += 15
            elif rate_diff >= 0.25: score += 8
            elif rate_diff > 0: score += 3

            # Equity (0-20)
            if equity_pct >= 40: score += 20
            elif equity_pct >= 30: score += 17
            elif equity_pct >= 20: score += 14
            elif equity_pct >= 10: score += 8
            elif equity_pct >= 5: score += 4

            # Loan size (0-15)
            if remaining_balance >= 500000: score += 15
            elif remaining_balance >= 400000: score += 13
            elif remaining_balance >= 300000: score += 10
            elif remaining_balance >= 200000: score += 7
            elif remaining_balance >= 100000: score += 4
            else: score += 1

            # Time in loan (0-10)
            if months_passed >= 36: score += 10
            elif months_passed >= 24: score += 8
            elif months_passed >= 18: score += 6
            elif months_passed >= 12: score += 4
            elif months_passed >= 6: score += 2

            # Rate trend (0-10)
            score += 5 if rate_diff > 0 else 0

            # Breakeven (0-10)
            closing_costs = remaining_balance * DEFAULT_CLOSING_COST_PCT
            savings = calculate_rate_savings(current_rate_pct, market_rate, remaining_balance, 360)
            ms = savings["monthly_savings"]
            if ms > 0:
                be = closing_costs / ms
                if be <= 12: score += 10
                elif be <= 24: score += 7
                elif be <= 36: score += 4
                elif be <= 48: score += 2

            score = min(100, max(0, score))
            refi_opportunity = score >= 50
            estimated_savings = round(savings["annual_savings"], 2) if refi_opportunity else 0

            if not dry_run:
                db.execute(text("""
                    UPDATE mum_clients SET
                        current_property_value = :val,
                        estimated_equity = :equity,
                        current_ltv = :ltv,
                        maturity_date = :maturity,
                        refi_score = :score,
                        refinance_opportunity = :refi_opp,
                        estimated_savings = :est_savings
                    WHERE id = :cid
                """), {
                    "val": round(current_value, 2),
                    "equity": round(equity, 2),
                    "ltv": round(ltv, 1),
                    "maturity": maturity,
                    "score": score,
                    "refi_opp": refi_opportunity,
                    "est_savings": estimated_savings,
                    "cid": row.id,
                })

            updated += 1
        except Exception as e:
            logger.warning(f"Error recalculating MUM client {row.id}: {e}")
            errors += 1

    if not dry_run:
        db.commit()

    return {
        "message": f"{'DRY RUN: ' if dry_run else ''}Recalculated {updated}/{len(rows)} MUM clients",
        "total": len(rows),
        "updated": updated,
        "errors": errors,
        "dry_run": dry_run,
        "market_rate_used": market_rate,
    }
