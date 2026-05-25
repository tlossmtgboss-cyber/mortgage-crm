"""
Call Recording Retrieval Routes
================================
Provides endpoints to retrieve call recording metadata and URLs
from both vapi_calls and call_logs tables.

Recording URLs are never exposed directly — all responses use
HMAC-signed, time-limited playback URLs (CR-005).

Prefix: /api/v1/calls
"""

import logging
import os
from typing import Optional, List
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
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
# CR-004: Upload validation constants
# ---------------------------------------------------------------------------

ALLOWED_UPLOAD_FORMATS = {"wav", "mp3", "flac", "m4a", "ogg", "webm"}
ALLOWED_CONTENT_TYPES = {
    "audio/wav", "audio/x-wav", "audio/wave",
    "audio/mpeg", "audio/mp3",
    "audio/flac", "audio/x-flac",
    "audio/mp4", "audio/x-m4a", "audio/m4a", "audio/aac",
    "audio/ogg", "audio/vorbis",
    "audio/webm", "video/webm",
}
MAX_UPLOAD_SIZE_BYTES = 3_221_225_472  # 3 GB
MAX_DURATION_SECONDS = 28_800  # 8 hours


def _validate_recording_upload(filename: str, content_type: str, size: int) -> None:
    """
    Validate an uploaded recording file (CR-004).

    Raises HTTPException(413) for size violations, HTTPException(422) for
    format/content-type violations.
    """
    # Size check
    if size > MAX_UPLOAD_SIZE_BYTES:
        size_mb = size / (1024 * 1024)
        raise HTTPException(
            status_code=413,
            detail=f"Recording size {size_mb:.1f} MB exceeds maximum of 3 GB",
        )

    # Extension check
    ext = (filename.rsplit(".", 1)[-1] if "." in filename else "").lower()
    if ext not in ALLOWED_UPLOAD_FORMATS:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Unsupported file extension '.{ext}'. "
                f"Allowed: {', '.join(sorted(ALLOWED_UPLOAD_FORMATS))}"
            ),
        )

    # Content-type check
    ct = (content_type or "").lower().split(";")[0].strip()
    if ct and ct not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Unsupported content type '{ct}'. "
                f"Allowed types: {', '.join(sorted(ALLOWED_CONTENT_TYPES))}"
            ),
        )


# ---------------------------------------------------------------------------
# CR-005: Signed playback URL helpers (delegates to api.routes.call_recording)
# ---------------------------------------------------------------------------

def _signed_url(recording_id: str) -> str:
    """Return a signed playback URL path for a recording (1-hour TTL)."""
    from api.routes.call_recording import generate_signed_recording_url

    base_url = os.getenv("RAILWAY_PUBLIC_DOMAIN", os.getenv("BASE_URL", ""))
    if base_url and not base_url.startswith("http"):
        base_url = f"https://{base_url}"
    result = generate_signed_recording_url(recording_id, base_url=base_url)
    return result["url"]


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------

class RecordingResponse(BaseModel):
    call_id: str
    source: str  # 'vapi' or 'dialer'
    phone_number: Optional[str] = None
    direction: Optional[str] = None
    recording_url: Optional[str] = None  # signed playback URL (CR-005)
    stereo_recording_url: Optional[str] = None  # signed playback URL (CR-005)
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
        vapi_call_id = row[0]
        return RecordingResponse(
            call_id=vapi_call_id,
            source="vapi",
            phone_number=row[1],
            direction=row[2],
            recording_url=_signed_url(vapi_call_id) if row[3] else None,
            stereo_recording_url=_signed_url(f"{vapi_call_id}-stereo") if row[4] else None,
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
        dialer_call_id = row[0] or call_id
        return RecordingResponse(
            call_id=dialer_call_id,
            source="dialer",
            phone_number=row[1],
            direction="outbound",
            recording_url=_signed_url(dialer_call_id) if row[2] else None,
            stereo_recording_url=_signed_url(f"{dialer_call_id}-stereo") if row[3] else None,
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
        vapi_call_id = row[0]
        results.append(RecordingResponse(
            call_id=vapi_call_id,
            source="vapi",
            phone_number=row[1],
            direction=row[2],
            recording_url=_signed_url(vapi_call_id) if row[3] else None,
            stereo_recording_url=_signed_url(f"{vapi_call_id}-stereo") if row[4] else None,
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
        dialer_call_id = row[0] or "unknown"
        results.append(RecordingResponse(
            call_id=dialer_call_id,
            source="dialer",
            phone_number=row[1],
            direction="outbound",
            recording_url=_signed_url(dialer_call_id) if row[2] else None,
            stereo_recording_url=_signed_url(f"{dialer_call_id}-stereo") if row[3] else None,
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


# ---------------------------------------------------------------------------
# POST /api/v1/calls/upload — Multipart file upload with CR-004 validation
# ---------------------------------------------------------------------------

@router.post("/upload", summary="Upload a call recording file")
async def upload_call_recording(
    file: UploadFile = File(...),
    duration_seconds: Optional[int] = Query(None, ge=0, description="Recording duration in seconds"),
    lead_id: Optional[int] = Query(None),
    call_id: Optional[str] = Query(None, description="External call ID to associate"),
    current_user=Depends(current_user_dep),
    db: Session = Depends(get_db),
):
    """
    Upload a call recording file with validation (CR-004).

    - Max size: 3 GB
    - Max duration: 8 hours
    - Allowed formats: wav, mp3, flac, m4a, ogg, webm
    - Validates both file extension and content-type

    Returns a signed playback URL for the stored recording.
    """
    filename = file.filename or ""
    content_type = file.content_type or ""

    # Read file content with streaming size check to reject early
    chunks = []
    total_size = 0
    while True:
        chunk = await file.read(1024 * 1024)  # 1 MB chunks
        if not chunk:
            break
        total_size += len(chunk)
        if total_size > MAX_UPLOAD_SIZE_BYTES:
            raise HTTPException(
                status_code=413,
                detail=f"Recording exceeds maximum size of 3 GB",
            )
        chunks.append(chunk)

    # Validate format and content-type (size already checked above)
    _validate_recording_upload(filename, content_type, total_size)

    # Validate duration
    if duration_seconds is not None and duration_seconds > MAX_DURATION_SECONDS:
        raise HTTPException(
            status_code=422,
            detail=f"Recording duration {duration_seconds}s exceeds maximum of {MAX_DURATION_SECONDS}s (8 hours)",
        )

    # Store the recording (write to local uploads dir; in production this
    # would go to S3 with a presigned URL — the storage backend is pluggable)
    import uuid
    recording_id = str(uuid.uuid4())
    ext = (filename.rsplit(".", 1)[-1] if "." in filename else "bin").lower()
    upload_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "uploads", "recordings")
    os.makedirs(upload_dir, exist_ok=True)
    dest_path = os.path.join(upload_dir, f"{recording_id}.{ext}")

    with open(dest_path, "wb") as f:
        for chunk in chunks:
            f.write(chunk)

    logger.info(
        "Recording uploaded: id=%s size=%d ext=%s user=%s",
        recording_id, total_size, ext, getattr(current_user, "id", None),
    )

    signed = _signed_url(recording_id)

    return {
        "success": True,
        "recording_id": recording_id,
        "size_bytes": total_size,
        "format": ext,
        "playback_url": signed,
    }
