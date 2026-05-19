"""
Aria Call Audit Trail Routes
=============================
User-facing API for LOs to review what Aria said on calls.
Queries vapi_calls for completed calls with transcripts, summaries,
and recordings. Scoped by organization_id for tenant isolation.

Prefix: /api/v1/aria/calls
"""
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from db import get_async_db
from routes.auth_deps import current_user_dep

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/aria/calls", tags=["Aria Call Audit"])

# Ensure user_id column exists on vapi_calls at import time
try:
    from vapi_models import ensure_vapi_ci_columns
    from database import SessionLocal as _SessionLocal
    _db = _SessionLocal()
    try:
        ensure_vapi_ci_columns(_db)
    finally:
        _db.close()
except Exception as _e:
    logger.debug("vapi_calls column migration (non-fatal): %s", _e)


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------

class CallSummaryItem(BaseModel):
    id: int
    vapi_call_id: str
    direction: Optional[str] = None
    status: Optional[str] = None
    phone_number: Optional[str] = None
    caller_name: Optional[str] = None
    lead_id: Optional[int] = None
    lead_name: Optional[str] = None
    duration: Optional[int] = None
    summary: Optional[str] = None
    sentiment: Optional[str] = None
    recording_url: Optional[str] = None
    has_transcript: bool = False
    started_at: Optional[str] = None
    ended_at: Optional[str] = None
    created_at: Optional[str] = None


class CallDetailItem(CallSummaryItem):
    transcript: Optional[str] = None
    stereo_recording_url: Optional[str] = None
    intent: Optional[str] = None
    notes: list = []


class CallHistoryResponse(BaseModel):
    calls: list
    total: int
    page: int
    per_page: int
    has_more: bool


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_org_id(user) -> Optional[int]:
    if isinstance(user, dict):
        return user.get("organization_id")
    return getattr(user, "organization_id", None)


def _get_user_id(user) -> Optional[int]:
    if isinstance(user, dict):
        return user.get("id")
    return getattr(user, "id", None)


def _mask_phone(phone: str) -> str:
    """Mask phone number for display, showing only last 4 digits."""
    if not phone:
        return ""
    digits = "".join(c for c in phone if c.isdigit())
    if len(digits) >= 4:
        return f"***{digits[-4:]}"
    return phone


def _iso(dt) -> Optional[str]:
    if dt is None:
        return None
    if hasattr(dt, "isoformat"):
        return dt.isoformat()
    return str(dt)


# ---------------------------------------------------------------------------
# GET /api/v1/aria/calls — Paginated call history
# ---------------------------------------------------------------------------

@router.get("")
async def list_aria_calls(
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(20, ge=1, le=100, description="Items per page"),
    direction: Optional[str] = Query(None, description="Filter by direction: inbound or outbound"),
    lead_id: Optional[int] = Query(None, description="Filter by lead ID"),
    date_from: Optional[str] = Query(None, description="Filter from date (ISO format)"),
    date_to: Optional[str] = Query(None, description="Filter to date (ISO format)"),
    search: Optional[str] = Query(None, description="Search transcript/summary text"),
    db: AsyncSession = Depends(get_async_db),
    current_user=Depends(current_user_dep),
):
    """
    Get paginated Aria call history for the current user's organization.

    Returns calls with summaries, durations, and metadata. Use the detail
    endpoint to fetch full transcripts for individual calls.
    """
    org_id = _get_org_id(current_user)
    if not org_id:
        raise HTTPException(status_code=400, detail="Organization context required")

    # Build query with filters
    where_clauses = ["vc.organization_id = :org_id"]
    params = {"org_id": org_id}

    # Only show completed calls with some data
    where_clauses.append("vc.status IN ('completed', 'ended')")

    if direction and direction in ("inbound", "outbound"):
        where_clauses.append("vc.direction = :direction")
        params["direction"] = direction

    if lead_id:
        where_clauses.append("vc.lead_id = :lead_id")
        params["lead_id"] = lead_id

    if date_from:
        try:
            dt_from = datetime.fromisoformat(date_from.replace("Z", "+00:00"))
            where_clauses.append("vc.started_at >= :date_from")
            params["date_from"] = dt_from
        except ValueError:
            pass

    if date_to:
        try:
            dt_to = datetime.fromisoformat(date_to.replace("Z", "+00:00"))
            where_clauses.append("vc.started_at <= :date_to")
            params["date_to"] = dt_to
        except ValueError:
            pass

    if search:
        where_clauses.append(
            "(vc.transcript ILIKE :search OR vc.summary ILIKE :search "
            "OR vc.caller_name ILIKE :search)"
        )
        params["search"] = f"%{search}%"

    where_sql = " AND ".join(where_clauses)

    # Count total
    count_sql = f"SELECT COUNT(*) FROM vapi_calls vc WHERE {where_sql}"
    try:
        total = (await db.execute(text(count_sql), params)).scalar() or 0
    except Exception as e:
        logger.error("Call audit count query failed: %s", e)
        total = 0

    # Fetch page
    offset = (page - 1) * per_page
    params["limit"] = per_page
    params["offset"] = offset

    data_sql = f"""
        SELECT
            vc.id,
            vc.vapi_call_id,
            vc.direction,
            vc.status,
            vc.phone_number,
            vc.caller_name,
            vc.lead_id,
            vc.duration,
            vc.summary,
            vc.sentiment,
            vc.recording_url,
            vc.transcript IS NOT NULL AND vc.transcript != '' AS has_transcript,
            vc.started_at,
            vc.ended_at,
            vc.created_at,
            l.name AS lead_name
        FROM vapi_calls vc
        LEFT JOIN leads l ON l.id = vc.lead_id
        WHERE {where_sql}
        ORDER BY vc.started_at DESC NULLS LAST, vc.created_at DESC
        LIMIT :limit OFFSET :offset
    """

    try:
        rows = (await db.execute(text(data_sql), params)).fetchall()
    except Exception as e:
        logger.error("Call audit list query failed: %s", e)
        return CallHistoryResponse(
            calls=[], total=0, page=page, per_page=per_page, has_more=False
        )

    calls = []
    for r in rows:
        calls.append({
            "id": r.id,
            "vapi_call_id": r.vapi_call_id,
            "direction": r.direction,
            "status": r.status,
            "phone_number": r.phone_number,
            "caller_name": r.caller_name,
            "lead_id": r.lead_id,
            "lead_name": r.lead_name,
            "duration": r.duration,
            "summary": r.summary,
            "sentiment": r.sentiment,
            "recording_url": r.recording_url,
            "has_transcript": bool(r.has_transcript),
            "started_at": _iso(r.started_at),
            "ended_at": _iso(r.ended_at),
            "created_at": _iso(r.created_at),
        })

    return {
        "calls": calls,
        "total": total,
        "page": page,
        "per_page": per_page,
        "has_more": (page * per_page) < total,
    }


# ---------------------------------------------------------------------------
# GET /api/v1/aria/calls/stats — Aggregate stats
# ---------------------------------------------------------------------------

@router.get("/stats")
async def get_aria_call_stats(
    days: int = Query(30, ge=1, le=365, description="Number of days to look back"),
    db: AsyncSession = Depends(get_async_db),
    current_user=Depends(current_user_dep),
):
    """Get aggregate call statistics for the Aria call audit dashboard."""
    org_id = _get_org_id(current_user)
    if not org_id:
        raise HTTPException(status_code=400, detail="Organization context required")

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    try:
        row = (await db.execute(text("""
            SELECT
                COUNT(*) AS total_calls,
                COUNT(*) FILTER (WHERE direction = 'inbound') AS inbound_calls,
                COUNT(*) FILTER (WHERE direction = 'outbound') AS outbound_calls,
                COALESCE(AVG(duration), 0) AS avg_duration,
                COALESCE(SUM(duration), 0) AS total_duration,
                COUNT(*) FILTER (WHERE transcript IS NOT NULL AND transcript != '') AS calls_with_transcript,
                COUNT(*) FILTER (WHERE recording_url IS NOT NULL AND recording_url != '') AS calls_with_recording,
                COUNT(*) FILTER (WHERE sentiment = 'positive') AS positive_calls,
                COUNT(*) FILTER (WHERE sentiment = 'negative') AS negative_calls,
                COUNT(*) FILTER (WHERE sentiment = 'neutral') AS neutral_calls
            FROM vapi_calls
            WHERE organization_id = :org_id
              AND status IN ('completed', 'ended')
              AND (started_at >= :cutoff OR (started_at IS NULL AND created_at >= :cutoff))
        """), {"org_id": org_id, "cutoff": cutoff})).fetchone()
    except Exception as e:
        logger.error("Call audit stats query failed: %s", e)
        return {
            "total_calls": 0, "inbound_calls": 0, "outbound_calls": 0,
            "avg_duration": 0, "total_duration": 0,
            "calls_with_transcript": 0, "calls_with_recording": 0,
            "positive_calls": 0, "negative_calls": 0, "neutral_calls": 0,
            "period_days": days,
        }

    return {
        "total_calls": row.total_calls or 0,
        "inbound_calls": row.inbound_calls or 0,
        "outbound_calls": row.outbound_calls or 0,
        "avg_duration": round(float(row.avg_duration or 0)),
        "total_duration": int(row.total_duration or 0),
        "calls_with_transcript": row.calls_with_transcript or 0,
        "calls_with_recording": row.calls_with_recording or 0,
        "positive_calls": row.positive_calls or 0,
        "negative_calls": row.negative_calls or 0,
        "neutral_calls": row.neutral_calls or 0,
        "period_days": days,
    }


# ---------------------------------------------------------------------------
# GET /api/v1/aria/calls/{call_id} — Full call detail with transcript
# ---------------------------------------------------------------------------

@router.get("/{call_id}")
async def get_aria_call_detail(
    call_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user=Depends(current_user_dep),
):
    """
    Get full call detail including transcript and notes.

    The transcript is returned as raw text with speaker labels
    (e.g. ASSISTANT: ..., USER: ...) for display in the audit UI.
    """
    org_id = _get_org_id(current_user)
    if not org_id:
        raise HTTPException(status_code=400, detail="Organization context required")

    try:
        row = (await db.execute(text("""
            SELECT
                vc.id,
                vc.vapi_call_id,
                vc.direction,
                vc.status,
                vc.phone_number,
                vc.caller_name,
                vc.lead_id,
                vc.duration,
                vc.summary,
                vc.sentiment,
                vc.intent,
                vc.recording_url,
                vc.stereo_recording_url,
                vc.transcript,
                vc.started_at,
                vc.ended_at,
                vc.created_at,
                l.name AS lead_name
            FROM vapi_calls vc
            LEFT JOIN leads l ON l.id = vc.lead_id
            WHERE vc.id = :call_id AND vc.organization_id = :org_id
        """), {"call_id": call_id, "org_id": org_id})).fetchone()
    except Exception as e:
        logger.error("Call audit detail query failed: %s", e)
        raise HTTPException(status_code=500, detail="Failed to load call detail")

    if not row:
        raise HTTPException(status_code=404, detail="Call not found")

    # Fetch notes/action items
    notes = []
    try:
        note_rows = (await db.execute(text("""
            SELECT id, note_type, content, priority, completed, created_at
            FROM vapi_call_notes
            WHERE call_id = :call_id
            ORDER BY created_at ASC
        """), {"call_id": call_id})).fetchall()
        notes = [
            {
                "id": n.id,
                "type": n.note_type,
                "content": n.content,
                "priority": n.priority,
                "completed": n.completed,
                "created_at": _iso(n.created_at),
            }
            for n in note_rows
        ]
    except Exception as e:
        logger.debug("Could not fetch call notes (table may not exist): %s", e)

    return {
        "id": row.id,
        "vapi_call_id": row.vapi_call_id,
        "direction": row.direction,
        "status": row.status,
        "phone_number": row.phone_number,
        "caller_name": row.caller_name,
        "lead_id": row.lead_id,
        "lead_name": row.lead_name,
        "duration": row.duration,
        "summary": row.summary,
        "sentiment": row.sentiment,
        "intent": row.intent,
        "recording_url": row.recording_url,
        "stereo_recording_url": row.stereo_recording_url,
        "transcript": row.transcript,
        "has_transcript": bool(row.transcript),
        "started_at": _iso(row.started_at),
        "ended_at": _iso(row.ended_at),
        "created_at": _iso(row.created_at),
        "notes": notes,
    }
