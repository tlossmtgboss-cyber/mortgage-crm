"""Disposition reporting routes — aggregate call outcome analytics."""
import logging
from typing import Optional
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import text

from db import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/dispositions", tags=["dispositions"])


class LogDispositionRequest(BaseModel):
    call_log_id: Optional[str] = None
    lead_id: Optional[str] = None
    loan_id: Optional[str] = None
    organization_id: str
    disposition: str  # answered, voicemail, no_answer, busy, wrong_number, dnc, callback, transferred
    sub_disposition: Optional[str] = None
    call_direction: str = "outbound"
    call_duration_seconds: Optional[int] = None
    caller_phone: Optional[str] = None
    notes: Optional[str] = None
    follow_up_required: bool = False
    follow_up_date: Optional[str] = None
    source: str = "dialer"


@router.post("/log")
async def log_disposition(request: LogDispositionRequest, db=Depends(get_db)):
    """Log a call disposition."""
    try:
        from database.models.call_disposition import CallDisposition
        from datetime import datetime

        disp = CallDisposition(
            call_log_id=request.call_log_id,
            lead_id=request.lead_id,
            loan_id=request.loan_id,
            organization_id=request.organization_id,
            disposition=request.disposition,
            sub_disposition=request.sub_disposition,
            call_direction=request.call_direction,
            call_duration_seconds=request.call_duration_seconds,
            caller_phone=request.caller_phone,
            notes=request.notes,
            follow_up_required=request.follow_up_required,
            follow_up_date=datetime.fromisoformat(request.follow_up_date) if request.follow_up_date else None,
            source=request.source,
        )
        db.add(disp)
        db.commit()
        db.refresh(disp)
        return {"status": "logged", "disposition_id": disp.id}
    except Exception as e:
        logger.warning(f"Failed to log disposition: {e}")
        db.rollback()
        return {"status": "error", "detail": str(e)}


@router.get("/summary")
async def disposition_summary(
    organization_id: Optional[str] = None,
    lo_id: Optional[str] = None,
    days: int = 30,
    db=Depends(get_db),
):
    """Get disposition summary broken down by outcome."""
    params = {"days": days}
    filters = ["d.created_at >= CURRENT_DATE - :days"]

    if organization_id:
        filters.append("d.organization_id = :org_id")
        params["org_id"] = organization_id
    if lo_id:
        filters.append("d.user_id = :lo_id")
        params["lo_id"] = lo_id

    where_sql = " AND ".join(filters)

    try:
        rows = db.execute(text(f"""
            SELECT
                d.disposition,
                COUNT(*) as count,
                AVG(d.call_duration_seconds) as avg_duration,
                COUNT(CASE WHEN d.follow_up_required THEN 1 END) as follow_ups
            FROM call_dispositions d
            WHERE {where_sql}
            GROUP BY d.disposition
            ORDER BY count DESC
        """), params).mappings().all()

        total = sum(r["count"] for r in rows)

        return {
            "period_days": days,
            "total_calls": total,
            "dispositions": [
                {
                    "disposition": r["disposition"],
                    "count": r["count"],
                    "percentage": round((r["count"] / total) * 100, 1) if total > 0 else 0,
                    "avg_duration_seconds": round(float(r["avg_duration"] or 0), 0),
                    "follow_ups_required": r["follow_ups"] or 0,
                }
                for r in rows
            ],
        }
    except Exception as e:
        logger.warning(f"Disposition summary query failed: {e}")
        return {"period_days": days, "total_calls": 0, "dispositions": [], "error": str(e)}


@router.get("/contact-rate")
async def contact_rate(
    organization_id: Optional[str] = None,
    lo_id: Optional[str] = None,
    days: int = 30,
    db=Depends(get_db),
):
    """Get contact rate (answered vs total calls)."""
    params = {"days": days}
    filters = ["d.created_at >= CURRENT_DATE - :days"]

    if organization_id:
        filters.append("d.organization_id = :org_id")
        params["org_id"] = organization_id
    if lo_id:
        filters.append("d.user_id = :lo_id")
        params["lo_id"] = lo_id

    where_sql = " AND ".join(filters)

    try:
        result = db.execute(text(f"""
            SELECT
                COUNT(*) as total,
                COUNT(CASE WHEN d.disposition = 'answered' THEN 1 END) as answered,
                COUNT(CASE WHEN d.disposition = 'voicemail' THEN 1 END) as voicemail,
                COUNT(CASE WHEN d.disposition = 'no_answer' THEN 1 END) as no_answer,
                COUNT(CASE WHEN d.disposition = 'transferred' THEN 1 END) as transferred
            FROM call_dispositions d
            WHERE {where_sql}
        """), params).mappings().first()

        total = result["total"] or 0
        answered = result["answered"] or 0

        return {
            "period_days": days,
            "total_attempts": total,
            "answered": answered,
            "voicemail": result["voicemail"] or 0,
            "no_answer": result["no_answer"] or 0,
            "transferred": result["transferred"] or 0,
            "contact_rate": round((answered / total) * 100, 1) if total > 0 else 0,
        }
    except Exception as e:
        logger.warning(f"Contact rate query failed: {e}")
        return {"period_days": days, "total_attempts": 0, "contact_rate": 0, "error": str(e)}


@router.get("/by-hour")
async def dispositions_by_hour(
    organization_id: Optional[str] = None,
    days: int = 30,
    db=Depends(get_db),
):
    """Get disposition breakdown by hour of day (optimal call times)."""
    params = {"days": days}
    org_filter = ""
    if organization_id:
        org_filter = "AND d.organization_id = :org_id"
        params["org_id"] = organization_id

    try:
        rows = db.execute(text(f"""
            SELECT
                EXTRACT(HOUR FROM d.created_at) as hour,
                COUNT(*) as total,
                COUNT(CASE WHEN d.disposition = 'answered' THEN 1 END) as answered
            FROM call_dispositions d
            WHERE d.created_at >= CURRENT_DATE - :days {org_filter}
            GROUP BY hour
            ORDER BY hour
        """), params).mappings().all()

        return {
            "period_days": days,
            "by_hour": [
                {
                    "hour": int(r["hour"]),
                    "total": r["total"],
                    "answered": r["answered"],
                    "contact_rate": round((r["answered"] / r["total"]) * 100, 1) if r["total"] > 0 else 0,
                }
                for r in rows
            ],
        }
    except Exception as e:
        logger.warning(f"By-hour query failed: {e}")
        return {"period_days": days, "by_hour": [], "error": str(e)}
