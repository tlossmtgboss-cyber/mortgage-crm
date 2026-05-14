"""
Aria Voice Analytics Routes
============================
Dashboard API for voice usage statistics, common queries,
time-saved estimates, and conversation logs.

Scoped by organization_id for tenant isolation.
Prefix: /api/v1/aria
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import text

from db import get_db
from routes.auth_deps import current_user_dep

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/aria", tags=["Aria Analytics"])


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------

class VoiceUsageStats(BaseModel):
    """Voice usage statistics for an LO or org."""
    total_conversations: int = 0
    total_duration_minutes: float = 0.0
    avg_duration_seconds: float = 0.0
    completed_conversations: int = 0
    abandoned_conversations: int = 0
    error_conversations: int = 0
    tools_used_count: int = 0
    top_intents: List[Dict[str, Any]] = Field(default_factory=list)
    period_days: int = 30


class TimeSavedEstimate(BaseModel):
    """Time saved by using Aria vs manual CRM interaction."""
    total_minutes_saved: float = 0.0
    total_hours_saved: float = 0.0
    period_days: int = 30
    conversations: int = 0
    tool_breakdown: Dict[str, Any] = Field(default_factory=dict)


class CommonQuery(BaseModel):
    """A frequently used voice query."""
    intent: str
    count: int
    avg_duration_seconds: float = 0.0


class ConversationLogEntry(BaseModel):
    """A single conversation log entry."""
    session_id: str
    mode: str = "lo_assistant"
    started_at: Optional[str] = None
    ended_at: Optional[str] = None
    duration_seconds: int = 0
    outcome: Optional[str] = None
    tools_used: List[str] = Field(default_factory=list)
    intents_handled: List[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/stats", response_model=VoiceUsageStats)
async def get_aria_stats(
    period_days: int = Query(30, ge=1, le=365, description="Period in days"),
    current_user=Depends(current_user_dep),
    db: Session = Depends(get_db),
):
    """Get Aria voice usage statistics for the current user's organization.

    Returns conversation counts, durations, top intents, and tool usage.
    """
    org_id = getattr(current_user, "organization_id", None)
    user_id = getattr(current_user, "id", None)
    if not org_id:
        raise HTTPException(status_code=400, detail="Organization context required")

    cutoff = datetime.now(timezone.utc) - timedelta(days=period_days)

    try:
        # Query vapi_calls for voice conversation stats
        summary_row = db.execute(text("""
            SELECT
                COUNT(*) as total,
                COALESCE(SUM(
                    EXTRACT(EPOCH FROM (ended_at - started_at))
                ), 0) as total_duration_secs,
                COALESCE(AVG(
                    EXTRACT(EPOCH FROM (ended_at - started_at))
                ), 0) as avg_duration_secs
            FROM vapi_calls
            WHERE organization_id = :org_id
            AND created_at >= :cutoff
        """), {"org_id": org_id, "cutoff": cutoff}).fetchone()

        total = summary_row[0] if summary_row else 0
        total_duration_secs = float(summary_row[1]) if summary_row else 0
        avg_duration = float(summary_row[2]) if summary_row else 0

        # Count outcomes
        outcome_rows = db.execute(text("""
            SELECT status, COUNT(*) as cnt
            FROM vapi_calls
            WHERE organization_id = :org_id
            AND created_at >= :cutoff
            GROUP BY status
        """), {"org_id": org_id, "cutoff": cutoff}).fetchall()

        completed = 0
        abandoned = 0
        errors = 0
        for row in outcome_rows:
            status = (row[0] or "").lower()
            count = row[1]
            if status in ("completed", "ended"):
                completed += count
            elif status in ("failed", "error"):
                errors += count
            elif status in ("no_answer", "busy", "cancelled"):
                abandoned += count

        # Get tool usage counts from aria_call_logs if available
        tools_used_count = 0
        top_intents: List[Dict[str, Any]] = []
        try:
            tool_rows = db.execute(text("""
                SELECT
                    jsonb_array_elements_text(tools_used::jsonb) as tool_name,
                    COUNT(*) as cnt
                FROM vapi_calls
                WHERE organization_id = :org_id
                AND created_at >= :cutoff
                AND tools_used IS NOT NULL
                AND tools_used != '[]'
                GROUP BY tool_name
                ORDER BY cnt DESC
                LIMIT 15
            """), {"org_id": org_id, "cutoff": cutoff}).fetchall()
            for row in tool_rows:
                top_intents.append({"intent": row[0], "count": row[1]})
                tools_used_count += row[1]
        except Exception:
            # tools_used column may not exist or may not be JSONB
            pass

        return VoiceUsageStats(
            total_conversations=total,
            total_duration_minutes=round(total_duration_secs / 60, 1),
            avg_duration_seconds=round(avg_duration, 1),
            completed_conversations=completed,
            abandoned_conversations=abandoned,
            error_conversations=errors,
            tools_used_count=tools_used_count,
            top_intents=top_intents,
            period_days=period_days,
        )

    except Exception as e:
        logger.error("Aria stats query failed: %s", e, exc_info=True)
        # Return empty stats rather than 500
        return VoiceUsageStats(period_days=period_days)


@router.get("/common-queries", response_model=List[CommonQuery])
async def get_common_queries(
    period_days: int = Query(30, ge=1, le=365),
    limit: int = Query(20, ge=1, le=100),
    current_user=Depends(current_user_dep),
    db: Session = Depends(get_db),
):
    """Get most common voice queries/intents across the organization.

    Returns intent names sorted by frequency.
    """
    org_id = getattr(current_user, "organization_id", None)
    if not org_id:
        raise HTTPException(status_code=400, detail="Organization context required")

    cutoff = datetime.now(timezone.utc) - timedelta(days=period_days)

    try:
        rows = db.execute(text("""
            SELECT
                jsonb_array_elements_text(tools_used::jsonb) as tool_name,
                COUNT(*) as cnt,
                COALESCE(AVG(
                    EXTRACT(EPOCH FROM (ended_at - started_at))
                ), 0) as avg_dur
            FROM vapi_calls
            WHERE organization_id = :org_id
            AND created_at >= :cutoff
            AND tools_used IS NOT NULL
            AND tools_used != '[]'
            GROUP BY tool_name
            ORDER BY cnt DESC
            LIMIT :lim
        """), {"org_id": org_id, "cutoff": cutoff, "lim": limit}).fetchall()

        return [
            CommonQuery(
                intent=row[0],
                count=row[1],
                avg_duration_seconds=round(float(row[2]), 1),
            )
            for row in rows
        ]
    except Exception as e:
        logger.error("Common queries fetch failed: %s", e, exc_info=True)
        return []


@router.get("/time-saved", response_model=TimeSavedEstimate)
async def get_time_saved(
    period_days: int = Query(30, ge=1, le=365),
    current_user=Depends(current_user_dep),
    db: Session = Depends(get_db),
):
    """Estimate time saved by using Aria vs manual CRM interaction.

    Heuristic: each tool call saves 1-3 minutes of manual navigation,
    depending on the tool type.
    """
    org_id = getattr(current_user, "organization_id", None)
    user_id = getattr(current_user, "id", None)
    if not org_id:
        raise HTTPException(status_code=400, detail="Organization context required")

    cutoff = datetime.now(timezone.utc) - timedelta(days=period_days)

    # Manual time estimates per tool (in minutes)
    MANUAL_ESTIMATES = {
        "find_contact": 2.0,
        "find_contact_phone": 1.5,
        "find_contact_email": 1.5,
        "get_pipeline_metrics": 3.0,
        "get_pipeline_summary": 3.0,
        "get_task_queue": 2.0,
        "send_sms_message": 1.5,
        "send_email": 2.0,
        "create_task": 1.5,
        "book_appointment": 3.0,
        "get_loans_by_status": 2.5,
        "get_rate_quote": 2.0,
        "get_availability": 2.0,
        "drop_voicemail": 1.0,
        "send_bulk_sms_outreach": 5.0,
        "send_bulk_email_outreach": 5.0,
        "morning_briefing": 5.0,
        "pipeline_summary": 3.0,
        "check_loan_status": 2.0,
        "end_of_day_recap": 4.0,
        "compliance_status": 3.0,
        "chase_documents": 3.0,
    }

    try:
        # Count conversations
        conv_row = db.execute(text("""
            SELECT COUNT(*) FROM vapi_calls
            WHERE organization_id = :org_id
            AND created_at >= :cutoff
        """), {"org_id": org_id, "cutoff": cutoff}).scalar() or 0

        # Count tools used
        tool_breakdown: Dict[str, Any] = {}
        total_minutes_saved = 0.0

        try:
            tool_rows = db.execute(text("""
                SELECT
                    jsonb_array_elements_text(tools_used::jsonb) as tool_name,
                    COUNT(*) as cnt
                FROM vapi_calls
                WHERE organization_id = :org_id
                AND created_at >= :cutoff
                AND tools_used IS NOT NULL
                AND tools_used != '[]'
                GROUP BY tool_name
            """), {"org_id": org_id, "cutoff": cutoff}).fetchall()

            for row in tool_rows:
                tool_name = row[0]
                count = row[1]
                minutes = MANUAL_ESTIMATES.get(tool_name, 1.5)
                saved = minutes * count
                total_minutes_saved += saved
                tool_breakdown[tool_name] = {
                    "count": count,
                    "minutes_saved_per_use": minutes,
                    "total_minutes_saved": round(saved, 1),
                }
        except Exception:
            # Fallback: estimate based on conversation count
            total_minutes_saved = conv_row * 3.0  # ~3 min saved per conversation

        return TimeSavedEstimate(
            total_minutes_saved=round(total_minutes_saved, 1),
            total_hours_saved=round(total_minutes_saved / 60, 1),
            period_days=period_days,
            conversations=conv_row,
            tool_breakdown=tool_breakdown,
        )

    except Exception as e:
        logger.error("Time saved calculation failed: %s", e, exc_info=True)
        return TimeSavedEstimate(period_days=period_days)


@router.get("/conversations", response_model=List[ConversationLogEntry])
async def get_conversations(
    period_days: int = Query(7, ge=1, le=90),
    limit: int = Query(25, ge=1, le=100),
    mode: Optional[str] = Query(None, description="Filter by mode: lo_assistant, inbound_receptionist, outbound_followup"),
    current_user=Depends(current_user_dep),
    db: Session = Depends(get_db),
):
    """Get recent Aria conversation logs.

    Returns a list of conversations with session IDs, durations,
    outcomes, and tools used. Scoped to the user's organization.
    """
    org_id = getattr(current_user, "organization_id", None)
    if not org_id:
        raise HTTPException(status_code=400, detail="Organization context required")

    cutoff = datetime.now(timezone.utc) - timedelta(days=period_days)
    conditions = ["organization_id = :org_id", "created_at >= :cutoff"]
    params: Dict[str, Any] = {"org_id": org_id, "cutoff": cutoff, "lim": limit}

    if mode:
        conditions.append("call_type = :mode")
        params["mode"] = mode

    where = " AND ".join(conditions)

    try:
        rows = db.execute(text(f"""
            SELECT
                vapi_call_id,
                COALESCE(call_type, 'lo_assistant') as mode,
                started_at,
                ended_at,
                COALESCE(
                    EXTRACT(EPOCH FROM (ended_at - started_at))::int,
                    0
                ) as duration_seconds,
                status,
                tools_used
            FROM vapi_calls
            WHERE {where}
            ORDER BY created_at DESC
            LIMIT :lim
        """), params).fetchall()

        results = []
        for row in rows:
            tools_list: List[str] = []
            try:
                import json
                if row[6]:
                    parsed = json.loads(row[6]) if isinstance(row[6], str) else row[6]
                    if isinstance(parsed, list):
                        tools_list = parsed
            except Exception:
                pass

            results.append(ConversationLogEntry(
                session_id=row[0] or "",
                mode=row[1] or "lo_assistant",
                started_at=row[2].isoformat() if row[2] else None,
                ended_at=row[3].isoformat() if row[3] else None,
                duration_seconds=row[4] or 0,
                outcome=row[5] or "unknown",
                tools_used=tools_list,
                intents_handled=tools_list,  # Same data for now
            ))

        return results

    except Exception as e:
        logger.error("Conversation log fetch failed: %s", e, exc_info=True)
        return []
