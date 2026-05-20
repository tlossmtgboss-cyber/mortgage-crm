"""
FastAPI routes for the Rate Watch system.

GET  /api/rate-watch/current-rates              — for the CRM rate ticker
GET  /api/rate-watch/history?product=&days=     — for the rate chart
GET  /api/rate-watch/opportunities              — LO dashboard, filterable
GET  /api/rate-watch/portfolio-summary          — aggregate portfolio stats
POST /api/rate-watch/margins                    — admin override
POST /api/rate-watch/borrower-targets           — set per-loan target rate
POST /api/rate-watch/admin/clear-drift-gate     — admin only; logs who & why
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text, and_, desc, func
from sqlalchemy.orm import Session

from database import get_db
from auth.dependencies import get_current_user
from database.models.rate_watch import (
    RateObservation,
    RateMarginConfig,
    BorrowerTargetRate,
    RefiOpportunityEvent,
    RateWatchRunLog,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/rate-watch", tags=["rate-watch"])


# ============================================================================
# Read endpoints
# ============================================================================

@router.get("/current-rates")
def get_current_rates(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Used by the CRM rate ticker. Returns latest rate per product with margin applied."""
    sql = text("""
        WITH latest_obs AS (
            SELECT DISTINCT ON (product)
                product,
                rate AS market_rate,
                points,
                observed_at,
                source,
                id AS observation_id
            FROM rate_observations
            WHERE observed_at > NOW() - INTERVAL '7 days'
            ORDER BY product, observed_at DESC
        ),
        active_margin AS (
            SELECT product, margin_bps
            FROM rate_margins
            WHERE scope = 'global' AND effective_to IS NULL
        )
        SELECT
            lo.product,
            lo.market_rate,
            lo.points,
            lo.observed_at,
            lo.source,
            lo.observation_id,
            COALESCE(am.margin_bps, 0) AS margin_bps,
            (lo.market_rate - COALESCE(am.margin_bps, 0)::NUMERIC / 100.0) AS perennia_rate
        FROM latest_obs lo
        LEFT JOIN active_margin am ON am.product = lo.product
        ORDER BY lo.product
    """)
    result = db.execute(sql)
    rows = result.mappings().all()

    now = datetime.now(timezone.utc)
    rates = []
    stale = False
    for r in rows:
        observed = r["observed_at"]
        if observed and (now - observed).total_seconds() > 24 * 3600:
            stale = True
        rates.append({
            "product": r["product"],
            "market_rate": str(r["market_rate"]),
            "points": str(r["points"]),
            "perennia_rate": str(r["perennia_rate"]),
            "margin_bps": int(r["margin_bps"]),
            "observed_at": observed.isoformat() if observed else None,
            "source": r["source"],
            "observation_id": int(r["observation_id"]),
        })

    return {
        "rates": rates,
        "fetched_at": now.isoformat(),
        "stale": stale,
    }


@router.get("/history")
def get_rate_history(
    product: str,
    days: Annotated[int, Query(ge=1, le=365)] = 30,
    source: str | None = None,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Historical rates for charting."""
    params = {"product": product, "days": days}
    source_filter = ""
    if source:
        source_filter = "AND source = :source"
        params["source"] = source

    sql = text(f"""
        SELECT product, source, rate, points, observed_at
        FROM rate_observations
        WHERE product = :product
          AND observed_at > NOW() - INTERVAL ':days days'
          {source_filter}
        ORDER BY observed_at ASC
    """.replace(":days days", f"{days} days"))
    result = db.execute(sql, params)
    rows = result.mappings().all()
    return [
        {
            "product": r["product"],
            "source": r["source"],
            "rate": str(r["rate"]),
            "points": str(r["points"]),
            "observed_at": r["observed_at"].isoformat() if r["observed_at"] else None,
        }
        for r in rows
    ]


# ============================================================================
# Opportunities — LO dashboard
# ============================================================================

@router.get("/opportunities")
def list_opportunities(
    statuses: str | None = Query(None, description="Comma-separated statuses"),
    loan_officer_id: int | None = None,
    since: str | None = None,
    limit: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Returns refi opportunities. LOs see only their own; admins see all."""
    conditions = []
    params = {}

    user_role = getattr(current_user, "role", "loan_officer")
    user_id = getattr(current_user, "id", None)

    if user_role not in ("admin", "platform_admin", "site_admin"):
        conditions.append("loan_officer_id = :lo_id")
        params["lo_id"] = user_id
    elif loan_officer_id:
        conditions.append("loan_officer_id = :lo_id")
        params["lo_id"] = loan_officer_id

    if statuses:
        status_list = [s.strip() for s in statuses.split(",")]
        conditions.append("status = ANY(:statuses)")
        params["statuses"] = status_list

    if since:
        conditions.append("detected_at >= :since")
        params["since"] = since

    where_sql = " AND ".join(conditions) if conditions else "TRUE"
    params["limit"] = limit

    sql = text(f"""
        SELECT id, loan_id, borrower_id, loan_officer_id, product,
               target_rate, market_rate, perennia_rate, margin_bps_at_detection,
               current_balance, current_rate, current_payment, projected_payment,
               monthly_savings, estimated_break_even_months,
               status, detected_at, expires_at, outreach_dispatched_at
        FROM refi_opportunities
        WHERE {where_sql}
        ORDER BY detected_at DESC
        LIMIT :limit
    """)
    result = db.execute(sql, params)
    rows = result.mappings().all()
    return [dict(r) for r in rows]


@router.get("/portfolio-summary")
def get_portfolio_summary(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Aggregate stats for the rate monitoring dashboard."""
    user_role = getattr(current_user, "role", "loan_officer")
    user_id = getattr(current_user, "id", None)
    org_id = getattr(current_user, "organization_id", None)

    org_filter = "AND ro.organization_id = :org_id" if org_id else ""
    lo_filter = ""
    params = {"org_id": org_id}

    if user_role not in ("admin", "platform_admin", "site_admin", "manager"):
        lo_filter = "AND ro.loan_officer_id = :lo_id"
        params["lo_id"] = user_id

    sql = text(f"""
        SELECT
            COUNT(*) FILTER (WHERE status = 'detected') AS pending_opportunities,
            COUNT(*) FILTER (WHERE status = 'outreach_sent') AS outreach_sent,
            COUNT(*) FILTER (WHERE status = 'meeting_booked') AS meetings_booked,
            COUNT(*) FILTER (WHERE status = 'closed_won') AS closed_won,
            COALESCE(SUM(monthly_savings) FILTER (WHERE status IN ('detected','outreach_sent','meeting_booked')), 0) AS total_potential_savings,
            COUNT(*) FILTER (WHERE detected_at > NOW() - INTERVAL '24 hours') AS alerts_today,
            COUNT(*) FILTER (WHERE detected_at > NOW() - INTERVAL '7 days') AS alerts_this_week
        FROM refi_opportunities ro
        WHERE 1=1 {org_filter} {lo_filter}
    """)
    result = db.execute(sql, params)
    row = result.mappings().first()

    # Active targets count
    target_sql = text(f"""
        SELECT COUNT(*) AS active_targets
        FROM borrower_target_rates
        WHERE active = TRUE
          AND organization_id = :org_id
    """)
    target_result = db.execute(target_sql, {"org_id": org_id})
    target_row = target_result.mappings().first()

    return {
        "pending_opportunities": int(row["pending_opportunities"]) if row else 0,
        "outreach_sent": int(row["outreach_sent"]) if row else 0,
        "meetings_booked": int(row["meetings_booked"]) if row else 0,
        "closed_won": int(row["closed_won"]) if row else 0,
        "total_potential_savings": float(row["total_potential_savings"]) if row else 0,
        "alerts_today": int(row["alerts_today"]) if row else 0,
        "alerts_this_week": int(row["alerts_this_week"]) if row else 0,
        "active_targets": int(target_row["active_targets"]) if target_row else 0,
    }


# ============================================================================
# Admin: margin overrides
# ============================================================================

class MarginUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    product: str
    margin_bps: Annotated[int, Field(ge=-500, le=500)]
    scope: str = "global"
    loan_officer_id: int | None = None
    note: str | None = None


@router.post("/margins", status_code=status.HTTP_201_CREATED)
def set_margin(
    update: MarginUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Insert a new active margin (supersede prior). Versioned."""
    user_role = getattr(current_user, "role", "loan_officer")
    if user_role not in ("admin", "platform_admin", "site_admin"):
        raise HTTPException(403, "Admin role required")

    if update.scope == "lo_override" and update.loan_officer_id is None:
        raise HTTPException(400, "lo_override scope requires loan_officer_id")
    if update.scope == "global" and update.loan_officer_id is not None:
        raise HTTPException(400, "global scope must not have loan_officer_id")

    user_id = str(getattr(current_user, "id", "00000000-0000-0000-0000-000000000000"))

    if update.scope == "global":
        db.execute(text("""
            UPDATE rate_margins SET effective_to = NOW()
            WHERE product = :product AND scope = 'global' AND effective_to IS NULL
        """), {"product": update.product})
    else:
        db.execute(text("""
            UPDATE rate_margins SET effective_to = NOW()
            WHERE product = :product AND scope = 'lo_override'
              AND loan_officer_id = :lo_id AND effective_to IS NULL
        """), {"product": update.product, "lo_id": str(update.loan_officer_id)})

    result = db.execute(text("""
        INSERT INTO rate_margins
            (product, margin_bps, scope, loan_officer_id, created_by, note)
        VALUES (:product, :margin_bps, :scope, :lo_id, :created_by, :note)
        RETURNING id
    """), {
        "product": update.product,
        "margin_bps": update.margin_bps,
        "scope": update.scope,
        "lo_id": str(update.loan_officer_id) if update.loan_officer_id else None,
        "created_by": user_id,
        "note": update.note,
    })
    new_id = result.scalar()
    db.commit()
    return {"id": new_id, "status": "active"}


# ============================================================================
# Borrower target rate
# ============================================================================

class BorrowerTargetUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    loan_id: int
    product: str
    target_rate: Annotated[Decimal, Field(gt=Decimal("0"), lt=Decimal("30"))]
    min_monthly_savings: Decimal | None = None
    min_break_even_months: int | None = Field(default=None, ge=1, le=120)
    cooldown_days: int = Field(default=30, ge=1, le=365)


@router.post("/borrower-targets", status_code=status.HTTP_201_CREATED)
def set_borrower_target(
    payload: BorrowerTargetUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Set or replace the active target rate for a loan."""
    user_id = getattr(current_user, "id", None)
    org_id = getattr(current_user, "organization_id", None)

    db.execute(text("""
        UPDATE borrower_target_rates
        SET active = FALSE, updated_at = NOW()
        WHERE loan_id = :loan_id AND active = TRUE
    """), {"loan_id": payload.loan_id})

    result = db.execute(text("""
        INSERT INTO borrower_target_rates (
            borrower_id, loan_id, product, target_rate,
            min_monthly_savings, min_break_even_months,
            cooldown_days, source, organization_id, loan_officer_id
        ) VALUES (
            :borrower_id, :loan_id, :product, :target_rate,
            :min_savings, :min_be, :cooldown, 'lo_set', :org_id, :lo_id
        )
        RETURNING id
    """), {
        "borrower_id": str(user_id),
        "loan_id": payload.loan_id,
        "product": payload.product,
        "target_rate": payload.target_rate,
        "min_savings": payload.min_monthly_savings,
        "min_be": payload.min_break_even_months,
        "cooldown": payload.cooldown_days,
        "org_id": org_id,
        "lo_id": user_id,
    })
    new_id = result.scalar()
    db.commit()
    return {"id": new_id}


# ============================================================================
# Admin: schema-drift gate
# ============================================================================

@router.post("/admin/clear-drift-gate")
def clear_drift_gate(
    reason: str = Query(..., min_length=10, max_length=500),
    current_user=Depends(get_current_user),
):
    """Clears the schema-drift gate after human verification."""
    import redis as redis_lib
    user_role = getattr(current_user, "role", "loan_officer")
    if user_role not in ("admin", "platform_admin", "site_admin"):
        raise HTTPException(403, "Admin role required")

    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
    try:
        r = redis_lib.Redis.from_url(redis_url, decode_responses=True)
        current = r.get("rate_watch:emit_opportunities_disabled")
        if not current:
            return {"status": "already_clear"}
        r.delete("rate_watch:emit_opportunities_disabled")
        logger.info(
            "schema_drift_gate_cleared user=%s reason=%s previous=%s",
            getattr(current_user, "id", None), reason, current,
        )
        return {"status": "cleared", "previous_state": current}
    except Exception as e:
        logger.error("Redis unavailable for drift gate clear: %s", e)
        raise HTTPException(503, "Redis unavailable")
