"""
Rate Monitor Alert Routes (iOS-compatible)

Provides GET /api/v1/rate-monitor/alerts/carplay and GET /api/v1/rate-alerts
returning data formatted for the iOS CarPlay and BackgroundSyncManager
Codable structs (CPRateAlert and RateAlert respectively).

Both endpoints require authentication and return rate alert data
transformed from the rate_monitor_alerts table.
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc, text
from typing import List, Optional
from datetime import datetime, timezone
import logging

from database import get_db
from auth.dependencies import get_current_user
from database.models import User

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Rate Monitor"])


def _safe_float(value, default: float = 0.0) -> float:
    """Safely convert a value to float, returning default on failure."""
    if value is None:
        return default
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


def _loan_type_to_rate_type(loan_type: Optional[str], loan_term: Optional[int]) -> str:
    """Map loan_type + loan_term from RateMonitorTarget to the rate_type
    string that CPRateAlert expects (e.g. '30yr_fixed', 'fha', 'va')."""
    lt = (loan_type or "conventional").lower()
    if lt in ("fha", "va", "usda", "jumbo"):
        return lt
    # conventional / conforming -> term-based label
    term = loan_term if isinstance(loan_term, int) and loan_term > 0 else 30
    return f"{term}yr_fixed"


def _safe_timestamp(created_at) -> str:
    """Safely convert a created_at value to an ISO-8601 timestamp string."""
    if isinstance(created_at, datetime):
        return created_at.isoformat()
    elif created_at:
        return str(created_at)
    return datetime.now(timezone.utc).isoformat()


def _change_direction(market_rate: float, client_rate: float) -> str:
    """Determine rate change direction. Defaults to 'down' when equal."""
    if market_rate > client_rate:
        return "up"
    return "down"


def _alert_to_carplay_dict(alert_row: dict) -> Optional[dict]:
    """Transform a raw rate_monitor_alerts row (joined with target) into
    the JSON shape expected by CPRateAlert in CarPlayModels.swift.

    Returns None if the row is malformed (missing id).

    CPRateAlert fields (snake_case in JSON, camelCase after decoder):
        id: Int
        rate_type: String        -> e.g. "30yr_fixed", "fha"
        current_rate: Double     -> market_rate at alert time
        previous_rate: Double    -> client_rate at alert time
        change_direction: String -> "up" or "down"
        timestamp: String        -> ISO-8601
    """
    if not alert_row or not isinstance(alert_row, dict):
        return None

    row_id = alert_row.get("id")
    if row_id is None:
        return None

    client_rate = _safe_float(alert_row.get("client_rate"))
    market_rate = _safe_float(alert_row.get("market_rate"))

    return {
        "id": row_id,
        "rate_type": _loan_type_to_rate_type(
            alert_row.get("loan_type", "conventional"),
            alert_row.get("loan_term", 30),
        ),
        "current_rate": market_rate,
        "previous_rate": client_rate,
        "change_direction": _change_direction(market_rate, client_rate),
        "timestamp": _safe_timestamp(alert_row.get("created_at")),
    }


def _alert_to_background_dict(alert_row: dict) -> Optional[dict]:
    """Transform a raw rate_monitor_alerts row into the JSON shape expected
    by RateAlert in BackgroundSyncManager.swift.

    Returns None if the row is malformed (missing id).

    RateAlert fields (snake_case in JSON, camelCase after decoder):
        id: String
        product_name: String     -> human-readable label
        current_rate: Double     -> market_rate
        previous_rate: Double    -> client_rate
        change_direction: String -> "up" or "down"
        timestamp: String        -> ISO-8601 (decoded as Date)
    """
    if not alert_row or not isinstance(alert_row, dict):
        return None

    row_id = alert_row.get("id")
    if row_id is None:
        return None

    client_rate = _safe_float(alert_row.get("client_rate"))
    market_rate = _safe_float(alert_row.get("market_rate"))

    rate_type = _loan_type_to_rate_type(
        alert_row.get("loan_type", "conventional"),
        alert_row.get("loan_term", 30),
    )
    # Human-readable product name
    product_names = {
        "30yr_fixed": "30-Year Fixed",
        "15yr_fixed": "15-Year Fixed",
        "fha": "FHA",
        "va": "VA",
        "usda": "USDA",
        "jumbo": "Jumbo",
    }
    product_name = product_names.get(rate_type, rate_type.replace("_", " ").title())

    return {
        "id": str(row_id),
        "product_name": product_name,
        "current_rate": market_rate,
        "previous_rate": client_rate,
        "change_direction": _change_direction(market_rate, client_rate),
        "timestamp": _safe_timestamp(alert_row.get("created_at")),
    }


def _fetch_alerts(db: Session, user: User, limit: int, status: Optional[str]) -> list:
    """Query rate_monitor_alerts joined with rate_monitor_targets to get
    loan_type and loan_term. Scoped to user's organization via mum_clients.
    Falls back gracefully if tables don't exist or user is None."""
    if not user:
        return []
    try:
        org_id = getattr(user, "organization_id", None)
        sql = text("""
            SELECT
                a.id,
                a.alert_type,
                a.client_rate,
                a.market_rate,
                a.status,
                a.created_at,
                COALESCE(t.loan_type, 'conventional') AS loan_type,
                COALESCE(t.loan_term, 30) AS loan_term
            FROM rate_monitor_alerts a
            LEFT JOIN rate_monitor_targets t ON a.target_id = t.id
            LEFT JOIN mum_clients mc ON t.mum_client_id = mc.id
            WHERE (:status IS NULL OR a.status = :status)
              AND (:org_id IS NULL OR mc.organization_id = :org_id)
            ORDER BY a.created_at DESC
            LIMIT :limit
        """)
        rows = db.execute(sql, {"status": status, "limit": limit, "org_id": org_id}).mappings().all()
        return [dict(row) for row in rows] if rows else []
    except Exception as e:
        # Table may not exist yet (migration not run)
        logger.debug(f"rate_monitor_alerts query failed (table may not exist): {e}")
        try:
            db.rollback()
        except Exception as rollback_err:
            logger.debug(f"Rollback after rate_monitor query failure also failed: {rollback_err}")
        return []


def _safe_transform(rows: list, transform_fn) -> list:
    """Apply a transform function to each row, skipping any that fail.
    Filters out None results (from malformed rows) and logs errors."""
    results = []
    for row in rows:
        try:
            item = transform_fn(row)
            if item is not None:
                results.append(item)
        except Exception as e:
            row_id = row.get("id", "unknown") if isinstance(row, dict) else "unknown"
            logger.warning(f"Skipping malformed rate alert row id={row_id}: {e}")
    return results


@router.get("/api/v1/rate-monitor/alerts/carplay")
async def get_rate_monitor_alerts(
    limit: int = Query(20, ge=1, le=100),
    status: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return rate alerts formatted for the iOS CarPlay CPRateAlert model.

    Response is a plain JSON array so the CarPlay getArray decoder can
    parse it directly as [CPRateAlert]. Returns [] when no alerts exist.
    """
    rows = _fetch_alerts(db, current_user, limit, status)
    return _safe_transform(rows, _alert_to_carplay_dict)


@router.get("/api/v1/rate-alerts")
async def get_rate_alerts(
    limit: int = Query(10, ge=1, le=100),
    status: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return rate alerts formatted for the iOS BackgroundSyncManager RateAlert model.

    Response is a plain JSON array so the BackgroundSyncManager decoder
    can parse it directly as [RateAlert]. Returns [] when no alerts exist.
    """
    rows = _fetch_alerts(db, current_user, limit, status)
    return _safe_transform(rows, _alert_to_background_dict)
