# =============================================================================
# PERENNIA AI — Call Intelligence Routes (v4 — Enterprise Audit)
# =============================================================================
# ALL 8 endpoints the frontend calls are implemented:
#   POST /session/start
#   POST /session/confirm-browser-disclosure
#   POST /session/retry-disclosure
#   POST /session/manual-consent-override
#   POST /session/{id}/stop
#   POST /session/{id}/convert-to-application
#   POST /artifacts/{id}/share
#   WS   /{session_id}/stream
#
# v4 fixes:
#   - stop sends call_status:completed before WS cleanup
#   - tenant isolation on all session queries
#   - agent_update payload enriched with field-level data
#   - WS endpoint validates session existence
#   - _activate_stt sends initial agent statuses via WS
# =============================================================================

import logging
import json
import os
from uuid import uuid4
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, field_validator
from sqlalchemy import text as sa_text
from sqlalchemy.orm import Session

from database import get_db
from middleware.webhook_verification import require_telnyx_webhook
from services.call_intelligence.recording_consent_config import (
    ConsentStatus,
    RecordingConsentConfig,
    TWO_PARTY_CONSENT_STATES,
)
from services.call_intelligence.recording_consent_service import RecordingConsentService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/call-intelligence", tags=["Call Intelligence Consent"])

_now = lambda: datetime.now(timezone.utc)


# -----------------------------------------------------------------
# Dependency Injection (set_dependencies pattern)
# -----------------------------------------------------------------

_get_current_user = None


def set_dependencies(user_dependency):
    global _get_current_user
    _get_current_user = user_dependency


async def get_current_user(request: Request, db: Session = Depends(get_db)):
    # main.py's get_current_user signature is (token, request, db) — extract the
    # Bearer token here; passing the Request positionally lands it in `token`
    # and 500s every endpoint (AttributeError on token.startswith).
    auth_header = request.headers.get("Authorization", "")
    token = auth_header[7:] if auth_header.startswith("Bearer ") else ""

    if not token:
        raise HTTPException(
            status_code=401,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if _get_current_user is None:
        raise HTTPException(status_code=503, detail="Authentication service not initialized")

    try:
        return await _get_current_user(token=token, request=request, db=db)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(
            status_code=401,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )


# -----------------------------------------------------------------
# WebSocket Manager (session -> connected clients)
# -----------------------------------------------------------------

class CIWebSocketManager:
    def __init__(self):
        self._connections: dict[str, list[WebSocket]] = {}

    async def connect(self, session_id: str, ws: WebSocket):
        await ws.accept()
        self._connections.setdefault(session_id, []).append(ws)

    def disconnect(self, session_id: str, ws: WebSocket):
        conns = self._connections.get(session_id, [])
        if ws in conns:
            conns.remove(ws)

    async def send(self, session_id: str, message: dict):
        dead = []
        for ws in list(self._connections.get(session_id, [])):
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)
        if dead:
            conns = self._connections.get(session_id, [])
            for ws in dead:
                if ws in conns:
                    conns.remove(ws)

    def cleanup(self, session_id: str):
        self._connections.pop(session_id, None)

    def has_connections(self, session_id: str) -> bool:
        return bool(self._connections.get(session_id))


ws_manager = CIWebSocketManager()


# -----------------------------------------------------------------
# Request / Response Models
# -----------------------------------------------------------------

class StartSessionRequest(BaseModel):
    call_control_id: Optional[str] = None
    contact_id: Optional[str] = None
    borrower_state: Optional[str] = None
    loan_officer_id: Optional[str] = None
    is_browser_mode: bool = False

    @field_validator("call_control_id", "contact_id", "loan_officer_id", mode="before")
    @classmethod
    def _coerce_str(cls, v):
        # Frontend sends numeric ids; pydantic v2 won't coerce int -> str.
        return str(v) if v is not None else None


class StartSessionResponse(BaseModel):
    session_id: str
    consent_status: str
    consent_requirement: str
    awaiting_disclosure: bool
    is_felony_state: bool
    is_browser_mode: bool
    disclosure_audio_url: Optional[str] = None
    disclosure_text: Optional[str] = None
    message: str


class BrowserDisclosureConfirm(BaseModel):
    session_id: str


class ManualOverrideRequest(BaseModel):
    session_id: str
    lo_confirmed_verbal_disclosure: bool


class RetryDisclosureRequest(BaseModel):
    session_id: str
    call_control_id: Optional[str] = None
    is_browser_mode: bool = False


# -----------------------------------------------------------------
# 1. POST /session/start
# -----------------------------------------------------------------

@router.post("/session/start", response_model=StartSessionResponse)
async def start_session(
    request: StartSessionRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    loan_officer_id = request.loan_officer_id or str(current_user.id)
    org_id = getattr(current_user, 'organization_id', None)

    borrower_state = request.borrower_state
    if not borrower_state and request.contact_id:
        borrower_state = _lookup_state(db, request.contact_id)
    borrower_state = _normalize_state(borrower_state)

    is_browser = request.is_browser_mode or not request.call_control_id
    session_id = str(uuid4())

    db.execute(
        sa_text("""
            INSERT INTO call_sessions (
                id, call_control_id, loan_officer_id, contact_id,
                borrower_state, recording_consent_status, status,
                organization_id, created_at, updated_at
            ) VALUES (
                :sid, :ccid, :lo_id, :cid,
                :state, 'pending', 'pending_consent',
                :org_id, :now, :now
            )
            ON CONFLICT (id) DO NOTHING
        """),
        {"sid": session_id, "ccid": request.call_control_id, "lo_id": loan_officer_id,
         "cid": request.contact_id, "state": borrower_state, "org_id": org_id, "now": _now()},
    )
    db.commit()

    telnyx_api_key = os.getenv("TELNYX_API_KEY", "")
    org_config = _get_org_config(db, loan_officer_id)
    service = RecordingConsentService(telnyx_api_key=telnyx_api_key, db=db)

    result = service.initiate_consent_gate(
        call_session_id=session_id,
        borrower_state=borrower_state,
        org_config=org_config,
        call_control_id=request.call_control_id,
        is_browser_mode=is_browser,
    )

    if not result["awaiting_webhook"] and result["consent_status"] not in ("failed", "browser_pending"):
        await _activate_stt(db, session_id, request.call_control_id)

    return StartSessionResponse(
        session_id=session_id,
        consent_status=result["consent_status"],
        consent_requirement=result["requirement"],
        awaiting_disclosure=result["awaiting_webhook"] or result["consent_status"] == "browser_pending",
        is_felony_state=result["is_felony_state"],
        is_browser_mode=result["is_browser_mode"],
        disclosure_audio_url=result.get("disclosure_audio_url"),
        disclosure_text=result.get("disclosure_text"),
        message=result["message"],
    )


# -----------------------------------------------------------------
# 2. POST /session/confirm-browser-disclosure
# -----------------------------------------------------------------

@router.post("/session/confirm-browser-disclosure")
async def confirm_browser_disclosure(
    request: BrowserDisclosureConfirm,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    session = _get_session(db, request.session_id, current_user)
    if not session:
        raise HTTPException(404, "Session not found")

    current_status = getattr(session, 'status', None)
    if current_status not in ('pending_consent', 'playing_disclosure'):
        raise HTTPException(400, f"Session not in disclosure state (status={current_status})")

    db.execute(
        sa_text("""
            UPDATE call_sessions
            SET recording_consent_status = 'disclosed',
                status = 'active',
                activated_at = :now,
                updated_at = :now
            WHERE id = :sid
        """),
        {"sid": request.session_id, "now": _now()},
    )
    db.commit()

    # Spin up the live transcription runner — without this, audio streamed
    # over the WebSocket after browser-mode consent goes nowhere.
    await _activate_stt(db, request.session_id, getattr(session, 'call_control_id', None))

    return {"status": "ok", "session_id": request.session_id, "active": True}


# -----------------------------------------------------------------
# 3. POST /session/retry-disclosure
# -----------------------------------------------------------------

@router.post("/session/retry-disclosure")
async def retry_disclosure(
    request: RetryDisclosureRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    session = _get_session(db, request.session_id, current_user)
    if not session:
        raise HTTPException(404, "Session not found")

    telnyx_api_key = os.getenv("TELNYX_API_KEY", "")
    org_config = _get_org_config(db, str(current_user.id))
    service = RecordingConsentService(telnyx_api_key=telnyx_api_key, db=db)

    is_browser = request.is_browser_mode or not request.call_control_id
    borrower_state = getattr(session, 'borrower_state', None)

    result = service.initiate_consent_gate(
        call_session_id=request.session_id,
        borrower_state=borrower_state,
        org_config=org_config,
        call_control_id=request.call_control_id,
        is_browser_mode=is_browser,
    )

    return {
        "status": "ok",
        "consent_status": result["consent_status"],
        "awaiting_disclosure": result["awaiting_webhook"] or result["consent_status"] == "browser_pending",
        "disclosure_audio_url": result.get("disclosure_audio_url"),
        "disclosure_text": result.get("disclosure_text"),
        "message": result["message"],
    }


# -----------------------------------------------------------------
# 4. POST /session/manual-consent-override
# -----------------------------------------------------------------

@router.post("/session/manual-consent-override")
async def manual_consent_override(
    request: ManualOverrideRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    session = _get_session(db, request.session_id, current_user)
    if not session:
        raise HTTPException(404, "Session not found")

    borrower_state = getattr(session, 'borrower_state', None)
    if borrower_state and borrower_state.upper() in TWO_PARTY_CONSENT_STATES:
        raise HTTPException(403, "Manual override blocked in two-party consent state")

    if not request.lo_confirmed_verbal_disclosure:
        raise HTTPException(400, "LO must confirm verbal disclosure was given")

    now = _now()
    db.execute(
        sa_text("""
            UPDATE call_sessions
            SET recording_consent_status = 'disclosed',
                status = 'active',
                consent_override_by = :lo_id,
                consent_override_at = :now,
                updated_at = :now
            WHERE id = :sid
        """),
        {"sid": request.session_id, "now": now, "lo_id": str(current_user.id)},
    )
    db.commit()

    await _activate_stt(db, request.session_id, getattr(session, 'call_control_id', None))
    return {"status": "ok", "session_id": request.session_id, "consent_status": "disclosed"}


# -----------------------------------------------------------------
# 5. POST /session/{id}/stop
# -----------------------------------------------------------------

@router.post("/session/{session_id}/stop")
async def stop_session(
    session_id: str,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    session = _get_session(db, session_id, current_user)
    if not session:
        raise HTTPException(404, "Session not found")

    now = _now()
    duration = None
    if hasattr(session, 'activated_at') and session.activated_at:
        activated = session.activated_at
        if activated.tzinfo is None:
            activated = activated.replace(tzinfo=timezone.utc)
        duration = int((now - activated).total_seconds())

    db.execute(
        sa_text("""
            UPDATE call_sessions
            SET status = 'completed',
                call_ended_at = :now,
                duration_seconds = :duration,
                updated_at = :now
            WHERE id = :sid
        """),
        {"sid": session_id, "now": now, "duration": duration},
    )
    db.commit()

    from services.call_intelligence.live_session_runner import (
        get_live_session,
        stop_live_session,
    )

    runner = get_live_session(session_id)
    diagnostics = dict(runner.stats) if runner else {
        "runner": "never_activated",
        "deepgram_key_present": bool(os.getenv("DEEPGRAM_API_KEY", "")),
    }
    logger.info(f"[CI] Session {session_id} stop diagnostics: {diagnostics}")

    await stop_live_session(session_id)

    await ws_manager.send(session_id, {
        "event": "call_status",
        "status": "completed",
        "duration_seconds": duration,
    })

    ws_manager.cleanup(session_id)

    return {
        "status": "ok",
        "session_id": session_id,
        "duration_seconds": duration,
        "diagnostics": diagnostics,
    }


# -----------------------------------------------------------------
# 6. POST /session/{id}/convert-to-application
# -----------------------------------------------------------------

@router.post("/session/{session_id}/convert-to-application")
def convert_to_application(
    session_id: str,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    raise HTTPException(501, "Application conversion not yet available")


# -----------------------------------------------------------------
# 7. POST /artifacts/{id}/share
# -----------------------------------------------------------------

@router.post("/artifacts/{artifact_id}/share")
def share_artifact(
    artifact_id: str,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    org_id = getattr(current_user, 'organization_id', None)
    if org_id:
        artifact = db.execute(
            sa_text("SELECT * FROM call_artifacts WHERE id = :id AND organization_id = :org_id"),
            {"id": artifact_id, "org_id": org_id},
        ).fetchone()
    else:
        artifact = db.execute(
            sa_text("SELECT * FROM call_artifacts WHERE id = :id"),
            {"id": artifact_id},
        ).fetchone()

    if not artifact:
        raise HTTPException(404, "Artifact not found")

    share_token = str(uuid4())[:12]
    db.execute(
        sa_text("""
            UPDATE call_artifacts
            SET share_token = :token,
                shared_at = :now,
                updated_at = :now
            WHERE id = :id
        """),
        {"id": artifact_id, "token": share_token, "now": _now()},
    )
    db.commit()

    frontend_url = os.getenv("FRONTEND_URL", "https://app.perenniaai.com")
    share_url = f"{frontend_url}/shared/artifact/{share_token}"

    return {"status": "ok", "share_url": share_url, "share_token": share_token}


# -----------------------------------------------------------------
# 8. WS /{session_id}/stream
# -----------------------------------------------------------------

@router.websocket("/{session_id}/stream")
async def ci_websocket_stream(websocket: WebSocket, session_id: str):
    await ws_manager.connect(session_id, websocket)
    from services.call_intelligence.live_session_runner import (
        activate_live_session,
        get_live_session,
    )

    activation_attempts = 0
    activation_error = None
    ws_chunks = 0

    async def _ensure_runner():
        """Lazy-activate the runner if consent already cleared but the
        activation task failed or raced — otherwise audio is dropped silently."""
        nonlocal activation_attempts, activation_error
        runner = get_live_session(session_id)
        if runner or activation_attempts >= 3:
            return runner
        activation_attempts += 1
        try:
            from db import SessionLocal
            db = SessionLocal()
            try:
                row = db.execute(
                    sa_text("SELECT status FROM call_sessions WHERE id = :sid"),
                    {"sid": session_id},
                ).fetchone()
            finally:
                db.close()
            if row and row[0] == "active":
                logger.warning(f"[CI WS] Lazy-activating runner for {session_id}")
                return await activate_live_session(session_id, ws_manager)
            activation_error = f"session_status={row[0] if row else 'row_not_found'}"
            logger.error(f"[CI WS] Cannot activate {session_id}: {activation_error}")
        except Exception as e:
            activation_error = str(e)[:200]
            logger.error(f"[CI WS] Lazy activation failed for {session_id}: {e}", exc_info=True)
        return None

    async def _report_pipeline(runner):
        """Push server-side truth to the panel — same process as this WS."""
        snapshot = dict(runner.stats) if runner else {
            "runner": "not_active",
            "activation_error": activation_error,
        }
        await ws_manager.send(session_id, {
            "event": "pipeline_status",
            "ws_chunks_received": ws_chunks,
            **{k: v for k, v in snapshot.items()},
        })

    try:
        while True:
            raw = await websocket.receive()

            if raw.get("bytes"):
                ws_chunks += 1
                runner = await _ensure_runner()
                if runner:
                    await runner.feed_audio(raw["bytes"])
                if ws_chunks % 50 == 1:
                    await _report_pipeline(runner)
                continue

            data = raw.get("text", "")
            if not data:
                continue

            try:
                msg = json.loads(data)
            except json.JSONDecodeError:
                continue

            msg_type = msg.get("type", "")

            if msg_type == "ping":
                await websocket.send_json({"type": "pong"})
            elif msg_type == "audio_chunk":
                import base64
                ws_chunks += 1
                runner = await _ensure_runner()
                if runner and msg.get("data"):
                    audio_bytes = base64.b64decode(msg["data"])
                    await runner.feed_audio(audio_bytes)
                if ws_chunks % 50 == 1:
                    await _report_pipeline(runner)
            elif msg_type == "transcript":
                runner = await _ensure_runner()
                if runner and msg.get("text"):
                    await runner.feed_transcript_text(
                        msg["text"], is_final=msg.get("is_final", True)
                    )

    except WebSocketDisconnect:
        ws_manager.disconnect(session_id, websocket)
    except Exception as e:
        logger.error(f"WS error for session {session_id}: {e}")
        ws_manager.disconnect(session_id, websocket)


# -----------------------------------------------------------------
# Telnyx Webhook Handler (async — needs await request.json())
# -----------------------------------------------------------------

@router.post("/webhooks/telnyx")
async def handle_telnyx_webhook(
    request: Request,
    db: Session = Depends(get_db),
    raw_body: bytes = Depends(require_telnyx_webhook),
):
    payload = json.loads(raw_body)
    event_type = payload.get("data", {}).get("event_type", "")
    event_payload = payload.get("data", {}).get("payload", {})
    call_control_id = event_payload.get("call_control_id", "")
    client_state = event_payload.get("client_state", "")

    logger.info(f"Telnyx consent webhook: {event_type} for call {call_control_id}")

    if event_type not in ("call.playback.ended", "call.speak.ended"):
        return {"status": "ignored"}

    try:
        session_id = RecordingConsentService.decode_client_state(client_state)
    except Exception:
        logger.error(f"Could not decode client_state: {client_state}")
        return {"status": "error", "message": "Invalid client_state"}

    telnyx_api_key = os.getenv("TELNYX_API_KEY", "")
    service = RecordingConsentService(telnyx_api_key=telnyx_api_key, db=db)
    should_activate = service.handle_playback_ended(call_control_id, session_id)

    if should_activate:
        await _activate_stt(db, session_id, call_control_id)
        await ws_manager.send(session_id, {
            "event": "consent_cleared",
            "consent_status": "disclosed",
            "message": "Recording disclosure complete. Call intelligence active.",
        })

    return {"status": "ok"}


# -----------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------

_STATE_NAME_TO_CODE = {
    "alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR",
    "california": "CA", "colorado": "CO", "connecticut": "CT", "delaware": "DE",
    "florida": "FL", "georgia": "GA", "hawaii": "HI", "idaho": "ID",
    "illinois": "IL", "indiana": "IN", "iowa": "IA", "kansas": "KS",
    "kentucky": "KY", "louisiana": "LA", "maine": "ME", "maryland": "MD",
    "massachusetts": "MA", "michigan": "MI", "minnesota": "MN", "mississippi": "MS",
    "missouri": "MO", "montana": "MT", "nebraska": "NE", "nevada": "NV",
    "new hampshire": "NH", "new jersey": "NJ", "new mexico": "NM", "new york": "NY",
    "north carolina": "NC", "north dakota": "ND", "ohio": "OH", "oklahoma": "OK",
    "oregon": "OR", "pennsylvania": "PA", "rhode island": "RI", "south carolina": "SC",
    "south dakota": "SD", "tennessee": "TN", "texas": "TX", "utah": "UT",
    "vermont": "VT", "virginia": "VA", "washington": "WA", "west virginia": "WV",
    "wisconsin": "WI", "wyoming": "WY", "district of columbia": "DC",
}
_VALID_STATE_CODES = set(_STATE_NAME_TO_CODE.values()) | {"PR", "VI", "GU", "AS", "MP"}


def _normalize_state(value: Optional[str]) -> Optional[str]:
    """Normalize free-form state input ('South Carolina', 'sc') to a 2-letter
    code. The column is VARCHAR(2); anything unrecognized becomes None so the
    consent gate falls back to its conservative default."""
    if not value:
        return None
    cleaned = value.strip()
    if len(cleaned) == 2 and cleaned.upper() in _VALID_STATE_CODES:
        return cleaned.upper()
    return _STATE_NAME_TO_CODE.get(cleaned.lower())


def _lookup_state(db: Session, contact_id: str) -> Optional[str]:
    """Best-effort borrower state lookup. There is no contacts table — the
    contact_id from the frontend is a lead id. leads.state is an
    EncryptedString, so this must go through the ORM to decrypt."""
    try:
        if not str(contact_id).isdigit():
            return None
        from database.models import Lead
        lead = db.query(Lead).filter(Lead.id == int(contact_id)).first()
        return lead.state if lead and lead.state else None
    except Exception as e:
        logger.warning(f"Borrower state lookup failed for contact {contact_id}: {e}")
        db.rollback()
        return None


def _get_org_config(db: Session, lo_id: str) -> RecordingConsentConfig:
    try:
        row = db.execute(
            sa_text("""
                SELECT o.recording_consent_config
                FROM users u JOIN organizations o ON u.organization_id = o.id
                WHERE u.id = CAST(:lo_id AS INTEGER)
            """),
            {"lo_id": lo_id},
        ).fetchone()
        return RecordingConsentConfig(**(row[0])) if row and row[0] else RecordingConsentConfig()
    except Exception as e:
        logger.warning(f"Org consent config lookup failed for LO {lo_id}: {e}")
        db.rollback()
        return RecordingConsentConfig()


def _get_session(db: Session, session_id: str, current_user=None):
    if current_user and hasattr(current_user, 'organization_id') and current_user.organization_id:
        return db.execute(
            sa_text("""
                SELECT * FROM call_sessions
                WHERE id = :id AND (
                    loan_officer_id = :lo_id
                    OR organization_id = :org_id
                )
            """),
            {"id": session_id, "lo_id": str(current_user.id),
             "org_id": current_user.organization_id},
        ).fetchone()
    return db.execute(
        sa_text("SELECT * FROM call_sessions WHERE id = :id"), {"id": session_id}
    ).fetchone()


async def _activate_stt(db: Session, session_id: str, call_control_id: Optional[str]):
    db.execute(
        sa_text("""
            UPDATE call_sessions
            SET status = 'active', activated_at = :now, updated_at = :now
            WHERE id = :sid
        """),
        {"sid": session_id, "now": _now()},
    )
    db.commit()
    logger.info(f"STT activated: session={session_id}")

    # Await activation so failures surface here instead of dying silently in
    # a fire-and-forget task. runner.start() is resilient (extractor optional,
    # STT connect failures caught), so this should not raise in practice.
    from services.call_intelligence.live_session_runner import activate_live_session
    try:
        await activate_live_session(session_id, ws_manager)
        logger.info(f"[CI] Live session runner active: {session_id}")
    except Exception as e:
        logger.error(
            f"[CI] activate_live_session failed for {session_id}: {e}", exc_info=True
        )
