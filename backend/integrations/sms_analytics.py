# backend/integrations/sms_analytics.py
# SMS analytics dashboard - aggregated metrics, trend data, per-agent stats

import logging
from typing import Optional, List

from sqlalchemy.orm import Session
from sqlalchemy import text

logger = logging.getLogger(__name__)


def get_dashboard_summary(db: Session, user_id: Optional[int] = None, days: int = 30) -> dict:
    """
    Master analytics summary for the SMS dashboard.
    Returns total sends, delivery rate, opt-out rate, cost estimate.
    """
    try:
        user_filter = "AND dl.user_id = :user_id" if user_id else ""
        params = {"days": days}
        if user_id:
            params["user_id"] = user_id

        row = db.execute(
            text(f"""
                SELECT
                    COUNT(*) AS total_sent,
                    COUNT(*) FILTER (WHERE dl.status = 'delivered') AS delivered,
                    COUNT(*) FILTER (WHERE dl.status = 'failed') AS failed,
                    ROUND(
                        COUNT(*) FILTER (WHERE dl.status = 'delivered')::numeric /
                        NULLIF(COUNT(*), 0) * 100, 2
                    ) AS delivery_rate,
                    SUM(dl.segments) AS total_segments,
                    ROUND(SUM(dl.segments) * 0.004, 4) AS estimated_cost_usd
                FROM sms_delivery_log dl
                WHERE dl.sent_at >= NOW() - INTERVAL '{days} days'
                {user_filter}
            """),
            params,
        ).fetchone()

        opt_out_count = _get_opt_out_count(db, days, user_id)
        compliance_blocks = _get_compliance_blocks(db, days, user_id)

        return {
            "period_days": days,
            "total_sent": row[0] if row else 0,
            "delivered": row[1] if row else 0,
            "failed": row[2] if row else 0,
            "delivery_rate_pct": float(row[3]) if row and row[3] else 0.0,
            "total_segments": row[4] if row and row[4] else 0,
            "estimated_cost_usd": float(row[5]) if row and row[5] else 0.0,
            "opt_outs": opt_out_count,
            "compliance_blocks": compliance_blocks,
        }
    except Exception as e:
        logger.error(f"Dashboard summary error: {e}")
        return {}


def get_daily_volume(
    db: Session,
    user_id: Optional[int] = None,
    days: int = 30,
) -> List[dict]:
    """Return daily SMS volume for trend chart (last N days)."""
    try:
        user_filter = "AND user_id = :user_id" if user_id else ""
        params = {"days": days}
        if user_id:
            params["user_id"] = user_id

        rows = db.execute(
            text(f"""
                SELECT
                    DATE(sent_at) AS send_date,
                    COUNT(*) AS total,
                    COUNT(*) FILTER (WHERE status = 'delivered') AS delivered,
                    COUNT(*) FILTER (WHERE status = 'failed') AS failed
                FROM sms_delivery_log
                WHERE sent_at >= NOW() - INTERVAL '{days} days'
                {user_filter}
                GROUP BY DATE(sent_at)
                ORDER BY send_date ASC
            """),
            params,
        ).fetchall()

        return [
            {
                "date": str(r[0]),
                "total": r[1],
                "delivered": r[2],
                "failed": r[3],
            }
            for r in rows
        ]
    except Exception as e:
        logger.error(f"Daily volume error: {e}")
        return []


def get_top_performing_templates(
    db: Session,
    user_id: Optional[int] = None,
    days: int = 30,
    limit: int = 10,
) -> List[dict]:
    """Return templates ranked by delivery rate."""
    try:
        user_filter = "AND dl.user_id = :user_id" if user_id else ""
        params = {"days": days, "limit": limit}
        if user_id:
            params["user_id"] = user_id

        rows = db.execute(
            text(f"""
                SELECT
                    t.name AS template_name,
                    COUNT(dl.id) AS sends,
                    ROUND(
                        COUNT(dl.id) FILTER (WHERE dl.status = 'delivered')::numeric /
                        NULLIF(COUNT(dl.id), 0) * 100, 1
                    ) AS delivery_rate
                FROM sms_delivery_log dl
                JOIN sms_templates t ON dl.template_id = t.id
                WHERE dl.sent_at >= NOW() - INTERVAL '{days} days'
                {user_filter}
                GROUP BY t.name
                ORDER BY delivery_rate DESC
                LIMIT :limit
            """),
            params,
        ).fetchall()

        return [
            {"template": r[0], "sends": r[1], "delivery_rate_pct": float(r[2]) if r[2] else 0.0}
            for r in rows
        ]
    except Exception as e:
        logger.error(f"Template analytics error: {e}")
        return []


def get_agent_leaderboard(
    db: Session,
    days: int = 30,
    limit: int = 10,
) -> List[dict]:
    """Return top agents by SMS sends and delivery rate."""
    try:
        rows = db.execute(
            text(f"""
                SELECT
                    u.email AS agent_email,
                    u.full_name AS agent_name,
                    COUNT(dl.id) AS total_sent,
                    ROUND(
                        COUNT(dl.id) FILTER (WHERE dl.status = 'delivered')::numeric /
                        NULLIF(COUNT(dl.id), 0) * 100, 1
                    ) AS delivery_rate
                FROM sms_delivery_log dl
                JOIN users u ON dl.user_id = u.id
                WHERE dl.sent_at >= NOW() - INTERVAL '{days} days'
                GROUP BY u.email, u.full_name
                ORDER BY total_sent DESC
                LIMIT :limit
            """),
            {"limit": limit},
        ).fetchall()

        return [
            {
                "agent": r[1] or r[0],
                "total_sent": r[2],
                "delivery_rate_pct": float(r[3]) if r[3] else 0.0,
            }
            for r in rows
        ]
    except Exception as e:
        logger.error(f"Leaderboard error: {e}")
        return []


def get_opt_out_trends(
    db: Session,
    user_id: Optional[int] = None,
    days: int = 30,
) -> List[dict]:
    """Return daily opt-out counts."""
    try:
        rows = db.execute(
            text(f"""
                SELECT DATE(opted_out_at) AS opt_date, COUNT(*) AS opt_outs
                FROM sms_opt_outs
                WHERE opted_out_at >= NOW() - INTERVAL '{days} days'
                GROUP BY DATE(opted_out_at)
                ORDER BY opt_date ASC
            """)
        ).fetchall()

        return [{"date": str(r[0]), "opt_outs": r[1]} for r in rows]
    except Exception as e:
        logger.error(f"Opt-out trends error: {e}")
        return []


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------
def _get_opt_out_count(db: Session, days: int, user_id: Optional[int]) -> int:
    try:
        row = db.execute(
            text(f"SELECT COUNT(*) FROM sms_opt_outs WHERE opted_out_at >= NOW() - INTERVAL '{days} days'")
        ).fetchone()
        return row[0] if row else 0
    except Exception:
        return 0


def _get_compliance_blocks(db: Session, days: int, user_id: Optional[int]) -> int:
    try:
        user_filter = "AND user_id = :user_id" if user_id else ""
        params = {"days": days}
        if user_id:
            params["user_id"] = user_id
        row = db.execute(
            text(f"SELECT COUNT(*) FROM sms_compliance_log WHERE check_result != 'passed' AND checked_at >= NOW() - INTERVAL '{days} days' {user_filter}"),
            params,
        ).fetchone()
        return row[0] if row else 0
    except Exception:
        return 0
