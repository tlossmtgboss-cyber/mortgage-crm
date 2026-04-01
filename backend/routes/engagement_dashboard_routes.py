"""Engagement dashboard routes — unified metrics across calls, texts, emails, and appointments."""
import logging
from typing import Optional
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends

from db import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/engagement-dashboard", tags=["engagement-dashboard"])


@router.get("/summary")
async def engagement_summary(
    lo_id: Optional[str] = None,
    organization_id: Optional[str] = None,
    days: int = 30,
    db=Depends(get_db),
):
    """Get engagement summary metrics across all channels."""
    from sqlalchemy import text
    params = {"days": days}
    lo_filter = ""
    org_filter = ""

    if lo_id:
        lo_filter = "AND a.user_id = :lo_id"
        params["lo_id"] = lo_id
    if organization_id:
        org_filter = "AND a.organization_id = :org_id"
        params["org_id"] = organization_id

    try:
        result = db.execute(text(f"""
            SELECT
                COUNT(*) as total_activities,
                COUNT(CASE WHEN a.type = 'Call' THEN 1 END) as calls,
                COUNT(CASE WHEN a.type = 'SMS' THEN 1 END) as texts,
                COUNT(CASE WHEN a.type = 'Email' THEN 1 END) as emails,
                COUNT(CASE WHEN a.type = 'Meeting' THEN 1 END) as meetings,
                COUNT(DISTINCT a.lead_id) as unique_leads
            FROM activities a
            WHERE a.created_at >= CURRENT_DATE - :days
            {lo_filter} {org_filter}
        """), params).mappings().first()

        return {
            "period_days": days,
            "total_activities": result["total_activities"] or 0,
            "by_channel": {
                "calls": result["calls"] or 0,
                "texts": result["texts"] or 0,
                "emails": result["emails"] or 0,
                "meetings": result["meetings"] or 0,
            },
            "unique_leads_contacted": result["unique_leads"] or 0,
        }
    except Exception as e:
        logger.warning(f"Engagement summary query failed: {e}")
        return {"period_days": days, "total_activities": 0, "by_channel": {}, "error": str(e)}


@router.get("/activity-feed")
async def activity_feed(
    lo_id: Optional[str] = None,
    organization_id: Optional[str] = None,
    limit: int = 50,
    db=Depends(get_db),
):
    """Get recent engagement activity feed."""
    from sqlalchemy import text
    params = {"limit": limit}
    filters = []

    if lo_id:
        filters.append("a.user_id = :lo_id")
        params["lo_id"] = lo_id
    if organization_id:
        filters.append("a.organization_id = :org_id")
        params["org_id"] = organization_id

    where_sql = " AND ".join(filters) if filters else "1=1"

    try:
        rows = db.execute(text(f"""
            SELECT
                a.id, a.type, a.content, a.sentiment,
                a.created_at,
                l.first_name, l.last_name,
                CONCAT(u.first_name, ' ', u.last_name) as user_name
            FROM activities a
            LEFT JOIN leads l ON l.id = a.lead_id
            LEFT JOIN users u ON u.id = a.user_id
            WHERE {where_sql}
            ORDER BY a.created_at DESC
            LIMIT :limit
        """), params).mappings().all()

        return {
            "count": len(rows),
            "activities": [
                {
                    "id": str(r["id"]),
                    "type": r["type"],
                    "content": (r["content"] or "")[:200],
                    "sentiment": r["sentiment"],
                    "lead_name": f"{r['first_name'] or ''} {r['last_name'] or ''}".strip(),
                    "user_name": r["user_name"],
                    "timestamp": r["created_at"].isoformat() if r["created_at"] else None,
                }
                for r in rows
            ],
        }
    except Exception as e:
        logger.warning(f"Activity feed query failed: {e}")
        return {"count": 0, "activities": [], "error": str(e)}


@router.get("/channel-comparison")
async def channel_comparison(
    organization_id: Optional[str] = None,
    days: int = 30,
    db=Depends(get_db),
):
    """Compare engagement effectiveness across channels."""
    from sqlalchemy import text
    params = {"days": days}
    org_filter = ""
    if organization_id:
        org_filter = "AND a.organization_id = :org_id"
        params["org_id"] = organization_id

    try:
        rows = db.execute(text(f"""
            SELECT
                a.type as channel,
                COUNT(*) as total,
                COUNT(DISTINCT a.lead_id) as unique_leads,
                COUNT(CASE WHEN a.sentiment = 'positive' THEN 1 END) as positive,
                COUNT(CASE WHEN a.sentiment = 'negative' THEN 1 END) as negative
            FROM activities a
            WHERE a.created_at >= CURRENT_DATE - :days
            {org_filter}
            GROUP BY a.type
            ORDER BY total DESC
        """), params).mappings().all()

        return {
            "period_days": days,
            "channels": [
                {
                    "channel": r["channel"],
                    "total": r["total"],
                    "unique_leads": r["unique_leads"],
                    "positive_sentiment": r["positive"] or 0,
                    "negative_sentiment": r["negative"] or 0,
                }
                for r in rows
            ],
        }
    except Exception as e:
        logger.warning(f"Channel comparison query failed: {e}")
        return {"period_days": days, "channels": [], "error": str(e)}


@router.get("/lo-leaderboard")
async def lo_leaderboard(
    organization_id: Optional[str] = None,
    days: int = 30,
    db=Depends(get_db),
):
    """Get LO engagement leaderboard."""
    from sqlalchemy import text
    params = {"days": days}
    org_filter = ""
    if organization_id:
        org_filter = "AND a.organization_id = :org_id"
        params["org_id"] = organization_id

    try:
        rows = db.execute(text(f"""
            SELECT
                u.id as lo_id,
                CONCAT(u.first_name, ' ', u.last_name) as lo_name,
                COUNT(*) as total_activities,
                COUNT(CASE WHEN a.type = 'Call' THEN 1 END) as calls,
                COUNT(CASE WHEN a.type = 'Email' THEN 1 END) as emails,
                COUNT(CASE WHEN a.type = 'SMS' THEN 1 END) as texts,
                COUNT(DISTINCT a.lead_id) as unique_leads
            FROM activities a
            JOIN users u ON u.id = a.user_id
            WHERE a.created_at >= CURRENT_DATE - :days
            {org_filter}
            GROUP BY u.id, u.first_name, u.last_name
            ORDER BY total_activities DESC
            LIMIT 20
        """), params).mappings().all()

        return {
            "period_days": days,
            "leaderboard": [
                {
                    "lo_id": str(r["lo_id"]),
                    "lo_name": r["lo_name"],
                    "total_activities": r["total_activities"],
                    "calls": r["calls"],
                    "emails": r["emails"],
                    "texts": r["texts"],
                    "unique_leads": r["unique_leads"],
                }
                for r in rows
            ],
        }
    except Exception as e:
        logger.warning(f"LO leaderboard query failed: {e}")
        return {"period_days": days, "leaderboard": [], "error": str(e)}


@router.get("/hourly-heatmap")
async def hourly_heatmap(
    organization_id: Optional[str] = None,
    days: int = 30,
    db=Depends(get_db),
):
    """Get hourly activity heatmap (hour-of-day x day-of-week)."""
    from sqlalchemy import text
    params = {"days": days}
    org_filter = ""
    if organization_id:
        org_filter = "AND a.organization_id = :org_id"
        params["org_id"] = organization_id

    try:
        rows = db.execute(text(f"""
            SELECT
                EXTRACT(DOW FROM a.created_at) as day_of_week,
                EXTRACT(HOUR FROM a.created_at) as hour,
                COUNT(*) as count
            FROM activities a
            WHERE a.created_at >= CURRENT_DATE - :days
            {org_filter}
            GROUP BY day_of_week, hour
            ORDER BY day_of_week, hour
        """), params).mappings().all()

        day_names = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
        heatmap = {}
        for r in rows:
            day = day_names[int(r["day_of_week"])]
            hour = int(r["hour"])
            if day not in heatmap:
                heatmap[day] = {}
            heatmap[day][hour] = r["count"]

        return {"period_days": days, "heatmap": heatmap}
    except Exception as e:
        logger.warning(f"Hourly heatmap query failed: {e}")
        return {"period_days": days, "heatmap": {}, "error": str(e)}


@router.get("/conversion-funnel")
async def conversion_funnel(
    organization_id: Optional[str] = None,
    days: int = 90,
    db=Depends(get_db),
):
    """Get lead conversion funnel metrics."""
    from sqlalchemy import text
    params = {"days": days}
    org_filter = ""
    if organization_id:
        org_filter = "AND l.organization_id = :org_id"
        params["org_id"] = organization_id

    try:
        result = db.execute(text(f"""
            SELECT
                COUNT(*) as total_leads,
                COUNT(CASE WHEN l.last_contact IS NOT NULL THEN 1 END) as contacted,
                COUNT(CASE WHEN l.ai_score >= 60 THEN 1 END) as qualified,
                COUNT(CASE WHEN l.loan_number IS NOT NULL THEN 1 END) as converted
            FROM leads l
            WHERE l.created_at >= CURRENT_DATE - :days
            {org_filter}
        """), params).mappings().first()

        total = result["total_leads"] or 0
        contacted = result["contacted"] or 0
        qualified = result["qualified"] or 0
        converted = result["converted"] or 0

        def pct(num, denom):
            return round((num / denom) * 100, 1) if denom > 0 else 0

        return {
            "period_days": days,
            "funnel": {
                "total_leads": total,
                "contacted": contacted,
                "qualified": qualified,
                "converted": converted,
            },
            "rates": {
                "contact_rate": pct(contacted, total),
                "qualification_rate": pct(qualified, contacted),
                "conversion_rate": pct(converted, qualified),
                "overall": pct(converted, total),
            },
        }
    except Exception as e:
        logger.warning(f"Conversion funnel query failed: {e}")
        return {"period_days": days, "funnel": {}, "rates": {}, "error": str(e)}
