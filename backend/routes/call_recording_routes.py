"""
Call Recording Retrieval Routes
================================
Provides endpoints to retrieve call recording metadata and URLs
from both vapi_calls and call_logs tables.

Prefix: /api/v1/calls
"""

import logging
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import text

from db import get_db
from routes.auth_deps import current_user_dep

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/calls", tags=["Call Recordings"])
lead_recordings_router = APIRouter(prefix="/api/v1/leads", tags=["Call Recordings"])


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------

class RecordingResponse(BaseModel):
    call_id: str
    source: str  # 'vapi' or 'dialer'
    phone_number: Optional[str] = None
    direction: Optional[str] = None
    recording_url: Optional[str] = None
    stereo_recording_url: Optional[str] = None
    recording_status: Optional[str] = None
    transcript: Optional[str] = None
    transcript_status: Optional[str] = None
    summary: Optional[str] = None
    duration_seconds: Optional[int] = None
    lead_id: Optional[int] = None
    created_at: Optional[str] = None


# ---------------------------------------------------------------------------
# GET /api/v1/calls/{call_id}/recording
# ---------------------------------------------------------------------------

@router.get("/{call_id}/recording", response_model=RecordingResponse)
async def get_call_recording(
    call_id: str,
    current_user=Depends(current_user_dep),
    db: Session = Depends(get_db),
):
    """
    Retrieve recording metadata and URL for a specific call.
    Searches vapi_calls first (by vapi_call_id or id), then call_logs.
    """
    org_id = getattr(current_user, "organization_id", None)

    # Try vapi_calls first (by vapi_call_id)
    row = db.execute(text("""
        SELECT vapi_call_id, phone_number, direction,
               recording_url, stereo_recording_url, recording_status,
               transcript, transcript_status, summary,
               duration, lead_id, created_at
        FROM vapi_calls
        WHERE (vapi_call_id = :cid OR CAST(id AS TEXT) = :cid)
          AND (organization_id = :org_id OR organization_id IS NULL)
        LIMIT 1
    """), {"cid": call_id, "org_id": org_id}).fetchone()

    if row:
        return RecordingResponse(
            call_id=row[0],
            source="vapi",
            phone_number=row[1],
            direction=row[2],
            recording_url=row[3],
            stereo_recording_url=row[4],
            recording_status=row[5] or "none",
            transcript=row[6],
            transcript_status=row[7] or ("completed" if row[6] else "none"),
            summary=row[8],
            duration_seconds=row[9],
            lead_id=row[10],
            created_at=row[11].isoformat() if row[11] else None,
        )

    # Fallback: try call_logs (by id or call_sid)
    row = db.execute(text("""
        SELECT COALESCE(call_sid, CAST(id AS TEXT)), contact_phone,
               recording_url, stereo_recording_url, recording_status,
               transcript_text, transcript_status,
               duration_seconds, lead_id, created_at
        FROM call_logs
        WHERE (call_sid = :cid OR CAST(id AS TEXT) = :cid)
          AND (organization_id = :org_id OR organization_id IS NULL)
        LIMIT 1
    """), {"cid": call_id, "org_id": org_id}).fetchone()

    if row:
        return RecordingResponse(
            call_id=row[0] or call_id,
            source="dialer",
            phone_number=row[1],
            direction="outbound",
            recording_url=row[2],
            stereo_recording_url=row[3],
            recording_status=row[4] or "none",
            transcript=row[5],
            transcript_status=row[6] or ("completed" if row[5] else "none"),
            summary=None,
            duration_seconds=row[7],
            lead_id=row[8],
            created_at=row[9].isoformat() if row[9] else None,
        )

    raise HTTPException(status_code=404, detail="Call not found")


# ---------------------------------------------------------------------------
# GET /api/v1/leads/{lead_id}/recordings
# ---------------------------------------------------------------------------

@lead_recordings_router.get(
    "/{lead_id}/recordings",
    response_model=List[RecordingResponse],
    summary="List recordings for a lead",
)
async def list_lead_recordings(
    lead_id: int,
    limit: int = Query(50, ge=1, le=200),
    current_user=Depends(current_user_dep),
    db: Session = Depends(get_db),
):
    """
    List all call recordings associated with a lead, newest first.
    Merges results from vapi_calls and call_logs.
    """
    org_id = getattr(current_user, "organization_id", None)
    results: list[RecordingResponse] = []

    # Vapi calls with a recording
    vapi_rows = db.execute(text("""
        SELECT vapi_call_id, phone_number, direction,
               recording_url, stereo_recording_url, recording_status,
               transcript, transcript_status, summary,
               duration, lead_id, created_at
        FROM vapi_calls
        WHERE lead_id = :lead_id
          AND (organization_id = :org_id OR organization_id IS NULL)
          AND recording_url IS NOT NULL AND recording_url != ''
        ORDER BY created_at DESC
        LIMIT :lim
    """), {"lead_id": lead_id, "org_id": org_id, "lim": limit}).fetchall()

    for row in vapi_rows:
        results.append(RecordingResponse(
            call_id=row[0],
            source="vapi",
            phone_number=row[1],
            direction=row[2],
            recording_url=row[3],
            stereo_recording_url=row[4],
            recording_status=row[5] or "none",
            transcript=row[6],
            transcript_status=row[7] or ("completed" if row[6] else "none"),
            summary=row[8],
            duration_seconds=row[9],
            lead_id=row[10],
            created_at=row[11].isoformat() if row[11] else None,
        ))

    # Dialer call_logs with a recording
    dialer_rows = db.execute(text("""
        SELECT COALESCE(call_sid, CAST(id AS TEXT)), contact_phone,
               recording_url, stereo_recording_url, recording_status,
               transcript_text, transcript_status,
               duration_seconds, lead_id, created_at
        FROM call_logs
        WHERE lead_id = :lead_id
          AND (organization_id = :org_id OR organization_id IS NULL)
          AND recording_url IS NOT NULL AND recording_url != ''
        ORDER BY created_at DESC
        LIMIT :lim
    """), {"lead_id": lead_id, "org_id": org_id, "lim": limit}).fetchall()

    for row in dialer_rows:
        results.append(RecordingResponse(
            call_id=row[0] or "unknown",
            source="dialer",
            phone_number=row[1],
            direction="outbound",
            recording_url=row[2],
            stereo_recording_url=row[3],
            recording_status=row[4] or "none",
            transcript=row[5],
            transcript_status=row[6] or ("completed" if row[5] else "none"),
            summary=None,
            duration_seconds=row[7],
            lead_id=row[8],
            created_at=row[9].isoformat() if row[9] else None,
        ))

    # Sort merged results by created_at descending
    results.sort(key=lambda r: r.created_at or "", reverse=True)
    return results[:limit]
