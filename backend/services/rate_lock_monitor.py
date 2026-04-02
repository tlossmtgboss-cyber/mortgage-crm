"""
Rate Lock Expiration Monitor Service

Monitors loans with approaching or expired rate locks and generates
alerts for loan officers. An expired rate lock means the borrower loses
their locked rate and may face a higher rate or need to renegotiate --
this directly costs the LO money and destroys borrower trust.

Usage:
    from services.rate_lock_monitor import check_expiring_locks, send_lock_alerts
"""

import logging
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

from services.workflow_constants import TERMINAL_LOAN_STAGES as TERMINAL_STAGES


def check_expiring_locks(
    db: Session,
    user_id: Optional[int] = None,
    organization_id: Optional[int] = None,
    hours_ahead: int = 48,
) -> Dict[str, Any]:
    """Check for loans with expiring or already-expired rate locks.

    Scans active (non-terminal) loans where lock_expiration_date is either
    already past or within the next ``hours_ahead`` hours.

    Args:
        db: SQLAlchemy session.
        user_id: If provided, only return locks for this LO's loans.
        organization_id: If provided, scope to this org.
        hours_ahead: Look-ahead window in hours (default 48).

    Returns:
        Dict with keys: expired, critical, warning, summary.
        Each bucket contains a list of alert dicts.
    """
    params: Dict[str, Any] = {"hours_ahead": hours_ahead}
    filters = [
        "l.lock_expiration_date IS NOT NULL",
        "l.stage NOT IN :terminal_stages",
        # Only include locks expiring within the window or already expired
        "l.lock_expiration_date <= (CURRENT_TIMESTAMP + make_interval(hours => :hours_ahead))",
    ]
    params["terminal_stages"] = tuple(TERMINAL_STAGES)

    if user_id is not None:
        filters.append("l.loan_officer_id = :user_id")
        params["user_id"] = user_id
    if organization_id is not None:
        filters.append("l.organization_id = :org_id")
        params["org_id"] = organization_id

    where_sql = " AND ".join(filters)

    sql = """
        SELECT
            l.id AS loan_id,
            l.loan_number,
            l.borrower_name,
            l.lock_expiration_date,
            l.rate,
            l.amount,
            l.stage,
            l.loan_officer_id,
            CONCAT(u.first_name, ' ', u.last_name) AS lo_name,
            EXTRACT(EPOCH FROM (l.lock_expiration_date - CURRENT_TIMESTAMP)) / 3600.0 AS hours_remaining
        FROM loans l
        LEFT JOIN users u ON u.id = l.loan_officer_id
        WHERE """ + where_sql + """
        ORDER BY l.lock_expiration_date ASC
    """
    query = text(sql)

    try:
        result = db.execute(query, params)
        rows = [dict(zip(result.keys(), row)) for row in result.fetchall()]
    except Exception as e:
        logger.exception("Failed to query expiring rate locks: %s", e)
        return {"expired": [], "critical": [], "warning": [], "summary": {"total": 0}}

    expired: List[Dict[str, Any]] = []
    critical: List[Dict[str, Any]] = []
    warning: List[Dict[str, Any]] = []

    for row in rows:
        hours_remaining = float(row["hours_remaining"] or 0)

        alert = {
            "loan_id": row["loan_id"],
            "loan_number": row["loan_number"],
            "borrower_name": row["borrower_name"] or "Unknown Borrower",
            "lock_expiration_date": row["lock_expiration_date"].isoformat() if row["lock_expiration_date"] else None,
            "hours_remaining": round(hours_remaining, 1),
            "rate": float(row["rate"]) if row["rate"] else None,
            "amount": float(row["amount"]) if row["amount"] else None,
            "stage": row["stage"],
            "loan_officer_id": row["loan_officer_id"],
            "lo_name": row["lo_name"],
        }

        if hours_remaining <= 0:
            alert["urgency"] = "expired"
            alert["hours_expired"] = round(abs(hours_remaining), 1)
            expired.append(alert)
        elif hours_remaining <= 24:
            alert["urgency"] = "critical"
            critical.append(alert)
        else:
            alert["urgency"] = "warning"
            warning.append(alert)

    summary = {
        "total": len(expired) + len(critical) + len(warning),
        "expired_count": len(expired),
        "critical_count": len(critical),
        "warning_count": len(warning),
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }

    return {
        "expired": expired,
        "critical": critical,
        "warning": warning,
        "summary": summary,
    }


def send_lock_alerts(
    db: Session,
    user_id: int,
    organization_id: Optional[int] = None,
) -> Dict[str, Any]:
    """Generate and optionally push rate lock expiration alerts for a user.

    Calls ``check_expiring_locks`` scoped to the given LO, builds
    notification payloads, and attempts to dispatch via the push
    notification service.  If push is unavailable the payloads are
    still returned so the caller (API route) can deliver them inline.

    Args:
        db: SQLAlchemy session.
        user_id: The loan officer's user ID.
        organization_id: Optional org scope.

    Returns:
        Dict with ``alerts`` list and ``push_result``.
    """
    lock_data = check_expiring_locks(
        db=db,
        user_id=user_id,
        organization_id=organization_id,
    )

    # Flatten all buckets into a single alert list, ordered by urgency
    all_alerts = lock_data["expired"] + lock_data["critical"] + lock_data["warning"]

    if not all_alerts:
        return {
            "alerts": [],
            "push_result": None,
            "summary": lock_data["summary"],
        }

    # Build notification payloads
    notifications = []
    for alert in all_alerts:
        urgency = alert["urgency"]
        borrower = alert["borrower_name"]
        hours = alert["hours_remaining"]

        if urgency == "expired":
            title = "Rate Lock EXPIRED"
            body = f"{borrower} -- lock expired {alert.get('hours_expired', 0):.0f}h ago"
        elif urgency == "critical":
            title = "Rate Lock Expiring Soon"
            body = f"{borrower} -- {hours:.0f}h remaining"
        else:
            title = "Rate Lock Warning"
            body = f"{borrower} -- {hours:.0f}h remaining"

        notifications.append({
            "type": "rate_lock_expiring",
            "urgency": urgency,
            "title": title,
            "body": body,
            "data": {
                "loan_id": alert["loan_id"],
                "loan_number": alert["loan_number"],
                "borrower_name": borrower,
                "hours_remaining": hours,
                "urgency": urgency,
            },
        })

    # Attempt push delivery
    push_result = None
    try:
        from services.push_notification_service import PushNotificationService
        push_svc = PushNotificationService()

        for notification in notifications:
            push_svc.send_to_user(
                db=db,
                user_id=user_id,
                notification_type="general",
                custom_title=notification["title"],
                custom_body=notification["body"],
                extra_data=notification["data"],
            )

        push_result = {"dispatched": len(notifications)}
        logger.info(
            "Dispatched %d rate lock alerts to user %d",
            len(notifications),
            user_id,
        )
    except ImportError:
        logger.debug("Push notification service not available; returning alerts inline only")
    except Exception as e:
        logger.warning("Push notification dispatch failed for user %d: %s", user_id, e)
        push_result = {"error": str(e)}

    return {
        "alerts": all_alerts,
        "notifications": notifications,
        "push_result": push_result,
        "summary": lock_data["summary"],
    }


def get_lock_summary_for_dashboard(
    db: Session,
    user_id: int,
    organization_id: Optional[int] = None,
) -> Dict[str, Any]:
    """Lightweight summary suitable for dashboard widgets.

    Returns just the counts and the single most urgent alert (if any),
    keeping the payload small for frequent polling.
    """
    lock_data = check_expiring_locks(
        db=db,
        user_id=user_id,
        organization_id=organization_id,
    )

    most_urgent = None
    if lock_data["expired"]:
        most_urgent = lock_data["expired"][0]
    elif lock_data["critical"]:
        most_urgent = lock_data["critical"][0]
    elif lock_data["warning"]:
        most_urgent = lock_data["warning"][0]

    return {
        "has_alerts": lock_data["summary"]["total"] > 0,
        "total": lock_data["summary"]["total"],
        "expired_count": lock_data["summary"]["expired_count"],
        "critical_count": lock_data["summary"]["critical_count"],
        "warning_count": lock_data["summary"]["warning_count"],
        "most_urgent": most_urgent,
    }
