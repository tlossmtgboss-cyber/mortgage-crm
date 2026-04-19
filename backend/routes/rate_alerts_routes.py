"""
Rate Alert Routes

Provides endpoints the iOS app expects for rate alerts:
  - GET /api/v1/rate-monitor/alerts   (SPA + general-purpose alert format)
  - GET /api/v1/rate-alerts           (BackgroundSyncManager alias)

Each alert returns: id, type, title, message, severity, created_at, loan_id.
Gracefully returns empty list when no rate monitoring data exists.
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import Optional
from datetime import datetime, timezone
import logging

from auth.dependencies import get_current_user
from db import get_db

logger = logging.getLogger(__name__)

router = APIRouter(tags=["rate-monitor"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_ALERT_TYPE_META = {
    "rate_target_hit": {
        "title": "Rate Target Hit",
        "severity": "critical",
    },
    "savings_threshold": {
        "title": "Savings Threshold Reached",
        "severity": "warning",
    },
    "rate_drop": {
        "title": "Rate Drop Alert",
        "severity": "info",
    },
    "lock_expiring": {
        "title": "Rate Lock Expiring Soon",
        "severity": "critical",
    },
    "relock_opportunity": {
        "title": "Relock Opportunity Available",
        "severity": "warning",
    },
    "float_down": {
        "title": "Float-Down Opportunity",
        "severity": "warning",
    },
    "rate_spike": {
        "title": "Rate Spike Alert",
        "severity": "warning",
    },
}


def _severity_for(alert_type: str, priority: Optional[str]) -> str:
    """Map alert_type + priority to a severity string (info/warning/critical)."""
    if priority == "urgent" or priority == "high":
        return "critical"
    meta = _ALERT_TYPE_META.get(alert_type)
    if meta:
        return meta["severity"]
    if priority == "low":
        return "info"
    return "warning"


def _title_for(alert_type: str) -> str:
    """Human-readable title for an alert_type."""
    meta = _ALERT_TYPE_META.get(alert_type)
    if meta:
        return meta["title"]
    return alert_type.replace("_", " ").title()


def _safe_float(value, default: float = 0.0) -> float:
    if value is None:
        return default
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


def _build_message(row: dict) -> str:
    """Build a human-readable message from an alert row."""
    alert_type = row.get("alert_type", "")
    client_rate = _safe_float(row.get("client_rate"))
    market_rate = _safe_float(row.get("market_rate"))
    monthly_savings = _safe_float(row.get("monthly_savings"))
    borrower = row.get("borrower_name") or "Client"

    if alert_type == "rate_target_hit":
        return (
            f"Rate target reached for {borrower}: "
            f"market rate {market_rate:.3f}% vs client rate {client_rate:.3f}%. "
            f"Est. savings ${monthly_savings:,.0f}/mo."
        )
    if alert_type == "savings_threshold":
        return (
            f"Savings threshold met for {borrower}: "
            f"est. ${monthly_savings:,.0f}/mo savings at {market_rate:.3f}%."
        )
    if alert_type == "lock_expiring":
        return f"Rate lock expiring soon for {borrower}."
    if alert_type == "relock_opportunity":
        return (
            f"Relock opportunity for {borrower}: "
            f"locked at {client_rate:.3f}%, market now {market_rate:.3f}%."
        )
    if alert_type == "float_down":
        return (
            f"Float-down available for {borrower}: "
            f"market dropped to {market_rate:.3f}%."
        )
    if alert_type in ("rate_drop", "rate_spike"):
        direction = "dropped" if alert_type == "rate_drop" else "spiked"
        return f"Rates have {direction}: market now {market_rate:.3f}%."

    # Fallback
    if market_rate and client_rate:
        return f"Rate alert: market {market_rate:.3f}% vs client {client_rate:.3f}%."
    return "Rate alert triggered."


def _safe_timestamp(value) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    if value:
        return str(value)
    return datetime.now(timezone.utc).isoformat()


def _row_to_alert(row: dict) -> Optional[dict]:
    """Transform a DB row into the unified alert format.

    Fields: id, type, title, message, severity, created_at, loan_id
    """
    row_id = row.get("id")
    if row_id is None:
        return None

    alert_type = row.get("alert_type", "rate_alert")
    priority = row.get("priority")

    return {
        "id": row_id,
        "type": alert_type,
        "title": _title_for(alert_type),
        "message": _build_message(row),
        "severity": _severity_for(alert_type, priority),
        "created_at": _safe_timestamp(row.get("created_at")),
        "loan_id": row.get("loan_id"),
        # Include rate fields for iOS CPRateAlert decoder compatibility
        "rate_type": _loan_type_label(
            row.get("loan_type", "conventional"),
            row.get("loan_term", 30),
        ),
        "current_rate": _safe_float(row.get("market_rate")),
        "previous_rate": _safe_float(row.get("client_rate")),
        "change_direction": (
            "up"
            if _safe_float(row.get("market_rate")) > _safe_float(row.get("client_rate"))
            else "down"
        ),
        "timestamp": _safe_timestamp(row.get("created_at")),
    }


def _loan_type_label(loan_type: Optional[str], loan_term: Optional[int]) -> str:
    lt = (loan_type or "conventional").lower()
    if lt in ("fha", "va", "usda", "jumbo"):
        return lt
    term = loan_term if isinstance(loan_term, int) and loan_term > 0 else 30
    return f"{term}yr_fixed"


def _fetch_alerts(
    db: Session,
    user,
    limit: int,
    status: Optional[str],
) -> list[dict]:
    """Query rate_monitor_alerts with graceful fallback when table is absent."""
    if not user:
        return []
    try:
        org_id = getattr(user, "organization_id", None)
        sql = text("""
            SELECT
                a.id,
                a.alert_type,
                a.priority,
                a.client_rate,
                a.market_rate,
                a.monthly_savings,
                a.status,
                a.created_at,
                COALESCE(t.loan_type, 'conventional') AS loan_type,
                COALESCE(t.loan_term, 30)              AS loan_term,
                t.borrower_name                         AS borrower_name,
                t.mum_client_id                         AS mum_client_id
            FROM rate_monitor_alerts a
            LEFT JOIN rate_monitor_targets t ON a.target_id = t.id
            LEFT JOIN mum_clients mc ON t.mum_client_id = mc.id
            WHERE (:status IS NULL OR a.status = :status)
              AND (:org_id IS NULL OR mc.organization_id = :org_id)
            ORDER BY a.created_at DESC
            LIMIT :limit
        """)
        rows = (
            db.execute(sql, {"status": status, "limit": limit, "org_id": org_id})
            .mappings()
            .all()
        )
        return [dict(r) for r in rows] if rows else []
    except Exception as e:
        logger.debug("rate_monitor_alerts query failed (table may not exist): %s", e)
        try:
            db.rollback()
        except Exception:
            pass
        return []


def _count_alerts(db: Session, user, status: Optional[str]) -> int:
    """Count matching alerts. Returns 0 on any failure."""
    if not user:
        return 0
    try:
        org_id = getattr(user, "organization_id", None)
        sql = text("""
            SELECT COUNT(*) AS cnt
            FROM rate_monitor_alerts a
            LEFT JOIN rate_monitor_targets t ON a.target_id = t.id
            LEFT JOIN mum_clients mc ON t.mum_client_id = mc.id
            WHERE (:status IS NULL OR a.status = :status)
              AND (:org_id IS NULL OR mc.organization_id = :org_id)
        """)
        row = db.execute(sql, {"status": status, "org_id": org_id}).scalar()
        return int(row) if row else 0
    except Exception:
        return 0


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/api/v1/rate-monitor/alerts")
async def get_rate_monitor_alerts(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    status: Optional[str] = None,
    priority: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Return rate alerts in the unified format expected by the SPA and iOS.

    Response: ``{"alerts": [...], "count": N}``

    Each alert has: id, type, title, message, severity, created_at, loan_id.
    Returns an empty list when no rate monitoring data exists.
    """
    rows = _fetch_alerts(db, current_user, limit, status)

    # Apply priority filter in Python (already small result set)
    if priority:
        rows = [
            r for r in rows
            if (r.get("priority") or "medium") == priority
        ]

    alerts = []
    for row in rows:
        try:
            alert = _row_to_alert(row)
            if alert is not None:
                alerts.append(alert)
        except Exception as e:
            logger.warning("Skipping malformed rate alert row: %s", e)

    count = _count_alerts(db, current_user, status)

    return {"alerts": alerts, "count": count}


@router.get("/api/v1/rate-alerts")
async def get_rate_alerts_alias(
    limit: int = Query(10, ge=1, le=100),
    status: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Alias endpoint used by iOS BackgroundSyncManager.

    Returns the same data as ``/api/v1/rate-monitor/alerts`` wrapped in
    ``{"alerts": [...], "count": N}``.  The iOS decoder tries a plain
    array first, then falls back to the ``alerts`` key.
    """
    rows = _fetch_alerts(db, current_user, limit, status)

    alerts = []
    for row in rows:
        try:
            alert = _row_to_alert(row)
            if alert is not None:
                alerts.append(alert)
        except Exception as e:
            logger.warning("Skipping malformed rate alert row: %s", e)

    return {"alerts": alerts, "count": len(alerts)}


# ---------------------------------------------------------------------------
# Registration helper
# ---------------------------------------------------------------------------

def register_rate_alerts_routes(app):
    """Register the rate alerts router on the FastAPI app.

    Usage in main.py::

        from routes.rate_alerts_routes import register_rate_alerts_routes
        register_rate_alerts_routes(app)
    """
    app.include_router(router, tags=["rate-monitor"])
    logger.info("Rate alerts routes registered")
