"""
Call Recording Retrieval Routes
================================
Provides endpoints to retrieve call recording metadata and URLs
from both vapi_calls and call_logs tables.

Prefix: /api/v1/calls
"""

import logging
from typing import Optional, List
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
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
          AND organization_id = :org_id
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
          AND organization_id = :org_id
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
          AND organization_id = :org_id
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
          AND organization_id = :org_id
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


# ---------------------------------------------------------------------------
# Allowed recording URL hosts (Vapi, Telnyx, Twilio CDNs + cloud storage)
# ---------------------------------------------------------------------------
_ALLOWED_RECORDING_HOSTS = {
    "api.vapi.ai",
    "storage.vapi.ai",
    "api.telnyx.com",
    "api.twilio.com",
    "recordings.telnyx.com",
}


def _is_allowed_recording_url(url: str) -> bool:
    """Only proxy URLs from known telephony/storage providers."""
    try:
        parsed = urlparse(url)
        host = (parsed.hostname or "").lower()
        if host in _ALLOWED_RECORDING_HOSTS:
            return True
        # Allow S3 / R2 / CloudFront storage
        if host.endswith(".amazonaws.com") or host.endswith(".r2.dev") or host.endswith(".cloudfront.net"):
            return True
        return False
    except Exception:
        return False


# ---------------------------------------------------------------------------
# GET /api/v1/calls/{call_id}/recording/stream
# Auth-gated proxy that streams the recording so raw CDN URLs are never
# exposed to the browser.
# ---------------------------------------------------------------------------

@router.get("/{call_id}/recording/stream")
async def stream_call_recording(
    call_id: str,
    channel: str = Query("mono", regex="^(mono|stereo)$"),
    current_user=Depends(current_user_dep),
    db: Session = Depends(get_db),
):
    """
    Stream a call recording through the API after verifying tenant access.
    The frontend should use this endpoint instead of loading CDN URLs directly,
    so that recordings are never accessible without authentication.
    """
    org_id = getattr(current_user, "organization_id", None)

    recording_url = None

    # 1. Try vapi_calls
    row = db.execute(text("""
        SELECT recording_url, stereo_recording_url
        FROM vapi_calls
        WHERE (vapi_call_id = :cid OR CAST(id AS TEXT) = :cid)
          AND organization_id = :org_id
        LIMIT 1
    """), {"cid": call_id, "org_id": org_id}).fetchone()

    if row:
        recording_url = row[1] if channel == "stereo" and row[1] else row[0]

    # 2. Fallback: call_logs
    if not recording_url:
        row = db.execute(text("""
            SELECT recording_url, stereo_recording_url
            FROM call_logs
            WHERE (call_sid = :cid OR CAST(id AS TEXT) = :cid)
              AND organization_id = :org_id
            LIMIT 1
        """), {"cid": call_id, "org_id": org_id}).fetchone()

        if row:
            recording_url = row[1] if channel == "stereo" and row[1] else row[0]

    if not recording_url:
        raise HTTPException(status_code=404, detail="Recording not found")

    # Validate the upstream URL against allowlist
    if not _is_allowed_recording_url(recording_url):
        logger.warning(
            "Recording URL host not in allowlist: %s (call_id=%s, org_id=%s)",
            recording_url[:80], call_id, org_id,
        )
        raise HTTPException(status_code=400, detail="Recording URL not from a trusted provider")

    # Stream the recording from the upstream provider
    import httpx

    try:
        client = httpx.AsyncClient(timeout=httpx.Timeout(connect=10, read=120, write=10, pool=10))
        upstream = await client.send(
            client.build_request("GET", recording_url),
            stream=True,
        )
        if upstream.status_code != 200:
            await upstream.aclose()
            await client.aclose()
            raise HTTPException(status_code=502, detail="Could not fetch recording from provider")

        content_type = upstream.headers.get("content-type", "audio/mpeg")
        content_length = upstream.headers.get("content-length")

        headers = {
            "Content-Disposition": f'inline; filename="recording-{call_id}.mp3"',
            "Cache-Control": "private, no-store",
        }
        if content_length:
            headers["Content-Length"] = content_length

        async def _stream():
            try:
                async for chunk in upstream.aiter_bytes(chunk_size=65536):
                    yield chunk
            finally:
                await upstream.aclose()
                await client.aclose()

        return StreamingResponse(
            _stream(),
            media_type=content_type,
            headers=headers,
        )
    except httpx.HTTPError as e:
        logger.error("Failed to stream recording %s: %s", call_id, e)
        raise HTTPException(status_code=502, detail="Could not fetch recording from provider")
