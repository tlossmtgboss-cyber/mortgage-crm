"""
Live Transfer Routes — Warm/cold transfer with LO whisper audio

Flow:
  1. AI or system initiates transfer → caller placed on hold
  2. LO dialed via Telnyx Call Control
  3. When LO answers, TTS whisper plays context (name, loan type, amount, credit)
  4. After whisper, both legs bridged into a Telnyx conference
"""

import os
import logging
import threading
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import text
import httpx

from db import get_db
from routes.auth_deps import current_user_flexible_dep
from services.voice_context_builder import build_transfer_whisper

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/telephony", tags=["Live Transfer"])

TELNYX_API_KEY = os.getenv("TELNYX_API_KEY", "")
TELNYX_API_BASE = "https://api.telnyx.com/v2"


# ---------------------------------------------------------------------------
# PERF-008: Circuit breaker for Telnyx API
# Opens after 5 consecutive failures, auto-resets after 30 seconds.
# ---------------------------------------------------------------------------

_telnyx_cb_lock = threading.Lock()
_telnyx_cb = {
    "consecutive_failures": 0,
    "open_since": None,          # datetime when circuit opened, or None if closed
    "threshold": 5,              # failures before opening
    "recovery_seconds": 30,      # seconds before half-open retry
}


def _telnyx_circuit_open() -> bool:
    """Check if the Telnyx circuit breaker is open (should reject calls)."""
    with _telnyx_cb_lock:
        if _telnyx_cb["open_since"] is None:
            return False
        elapsed = (datetime.now(timezone.utc) - _telnyx_cb["open_since"]).total_seconds()
        if elapsed >= _telnyx_cb["recovery_seconds"]:
            # Half-open: allow one request through to probe recovery
            logger.info("Telnyx circuit breaker half-open after %.1fs — allowing probe request", elapsed)
            return False
        return True


def _telnyx_circuit_record_success():
    """Record a successful Telnyx call — reset circuit breaker."""
    with _telnyx_cb_lock:
        if _telnyx_cb["consecutive_failures"] > 0 or _telnyx_cb["open_since"] is not None:
            logger.info(
                "Telnyx circuit breaker reset (was %d consecutive failures)",
                _telnyx_cb["consecutive_failures"],
            )
        _telnyx_cb["consecutive_failures"] = 0
        _telnyx_cb["open_since"] = None


def _telnyx_circuit_record_failure():
    """Record a Telnyx failure — may trip the circuit breaker."""
    with _telnyx_cb_lock:
        _telnyx_cb["consecutive_failures"] += 1
        count = _telnyx_cb["consecutive_failures"]
        if count >= _telnyx_cb["threshold"] and _telnyx_cb["open_since"] is None:
            _telnyx_cb["open_since"] = datetime.now(timezone.utc)
            logger.error(
                "Telnyx circuit breaker OPEN after %d consecutive failures — "
                "rejecting requests for %ds",
                count, _telnyx_cb["recovery_seconds"],
            )


# ---------------------------------------------------------------------------
# Pydantic request/response schemas
# ---------------------------------------------------------------------------

class InitiateTransferRequest(BaseModel):
    call_control_id: str
    target_lo_id: int
    lead_id: Optional[int] = None
    whisper_text: Optional[str] = None
    transfer_type: str = "warm"  # warm | cold


class TransferStatusResponse(BaseModel):
    transfer_id: str
    status: str
    lo_name: Optional[str] = None
    whisper_text: Optional[str] = None


# ---------------------------------------------------------------------------
# Telnyx helpers
# ---------------------------------------------------------------------------

async def _telnyx_post(path: str, payload: dict, _retries: int = 2) -> dict:
    """POST to Telnyx Call Control API with retry on transient errors.

    Protected by a circuit breaker (PERF-008): after 5 consecutive failures
    the circuit opens and requests are rejected for 30 seconds.
    """
    import asyncio as _asyncio

    # PERF-008: Circuit breaker fast-reject
    if _telnyx_circuit_open():
        logger.warning("Telnyx circuit breaker OPEN — rejecting request to %s", path)
        raise HTTPException(
            status_code=503,
            detail="Telephony provider temporarily unavailable (circuit open)",
        )

    last_exc = None
    for attempt in range(_retries + 1):
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.post(
                    f"{TELNYX_API_BASE}{path}",
                    json=payload,
                    headers={"Authorization": f"Bearer {TELNYX_API_KEY}", "Content-Type": "application/json"},
                )
                if resp.status_code >= 500 and attempt < _retries:
                    logger.warning(
                        "Telnyx API transient error %s on %s (attempt %d/%d)",
                        resp.status_code, path, attempt + 1, _retries + 1,
                    )
                    await _asyncio.sleep(0.5 * (attempt + 1))
                    continue
                if resp.status_code >= 400:
                    logger.error("Telnyx API error %s on %s: %s", resp.status_code, path, resp.text[:300])
                    _telnyx_circuit_record_failure()
                    raise HTTPException(status_code=502, detail="Telephony provider error")
                _telnyx_circuit_record_success()
                return resp.json() if resp.content else {}
        except HTTPException:
            raise
        except Exception as e:
            last_exc = e
            if attempt < _retries:
                logger.warning("Telnyx API request error on %s (attempt %d): %s", path, attempt + 1, e)
                await _asyncio.sleep(0.5 * (attempt + 1))
                continue
            logger.error("Telnyx API request failed after %d attempts on %s: %s", _retries + 1, path, e)
            _telnyx_circuit_record_failure()
            raise HTTPException(status_code=502, detail="Telephony provider error")
    _telnyx_circuit_record_failure()
    raise HTTPException(status_code=502, detail="Telephony provider error")


async def _hold_call(call_control_id: str, audio_url: Optional[str] = None):
    """Place a call leg on hold."""
    payload = {"audio_url": audio_url or "silence"}
    await _telnyx_post(f"/calls/{call_control_id}/actions/hold", payload)


async def _unhold_call(call_control_id: str):
    await _telnyx_post(f"/calls/{call_control_id}/actions/unhold", {})


async def _dial(to: str, from_: str, connection_id: str, client_state: str = "") -> dict:
    """Originate a new outbound call leg."""
    payload = {
        "to": to,
        "from": from_,
        "connection_id": connection_id,
        "webhook_url": os.getenv("TELNYX_WEBHOOK_URL", "") + "/api/v1/telephony/transfer-status",
        "client_state": client_state,
    }
    return await _telnyx_post("/calls", payload)


async def _speak(call_control_id: str, text: str, voice: str = "female", language: str = "en-US"):
    """Play TTS on a call leg."""
    payload = {"payload": text, "voice": voice, "language": language}
    await _telnyx_post(f"/calls/{call_control_id}/actions/speak", payload)


async def _create_conference(name: str) -> dict:
    """Create a Telnyx conference."""
    return await _telnyx_post("/conferences", {
        "name": name,
        "call_control_id": "none",
        "beep_enabled": "never",
    })


async def _join_conference(conference_id: str, call_control_id: str):
    """Add a call leg to a conference."""
    await _telnyx_post(f"/conferences/{conference_id}/actions/join", {
        "call_control_id": call_control_id,
    })


# ---------------------------------------------------------------------------
# Build whisper text from lead data
# ---------------------------------------------------------------------------

def _build_whisper(
    db: Session,
    lead_id: Optional[int],
    custom_text: Optional[str],
    organization_id: Optional[int] = None,
    current_call_summary: Optional[str] = None,
) -> str:
    """
    Build a TTS whisper script with cross-channel context.

    Uses the enhanced voice_context_builder for rich context including SMS
    history, voicemail drops, and current call summary. Falls back to basic
    lead data if the enhanced builder fails.
    """
    if custom_text:
        return custom_text

    if not lead_id:
        return "Incoming transfer. No lead data available."

    # Try enhanced whisper with cross-channel context
    try:
        enhanced = build_transfer_whisper(
            db, lead_id, organization_id, current_call_summary,
        )
        if enhanced and enhanced != "Incoming transfer. No lead data available.":
            return enhanced
    except Exception as e:
        logger.warning("Enhanced whisper build failed, using basic fallback: %s", e)

    # Fallback: basic lead data only
    try:
        row = db.execute(text("""
            SELECT l.first_name, l.last_name, l.loan_type, l.loan_amount,
                   l.credit_score, l.property_type
            FROM leads l WHERE l.id = :lid
        """), {"lid": lead_id}).fetchone()

        if not row:
            return "Incoming transfer. Lead details unavailable."

        parts = ["Incoming transfer."]
        name = f"{row.first_name or ''} {row.last_name or ''}".strip()
        if name:
            parts.append(f"Borrower: {name}.")
        if row.loan_type:
            parts.append(f"{row.loan_type.replace('_', ' ').title()} loan.")
        if row.loan_amount:
            parts.append(f"Amount: ${int(row.loan_amount):,}.")
        if row.credit_score:
            parts.append(f"Credit: {row.credit_score}.")
        if row.property_type:
            parts.append(f"Property: {row.property_type.replace('_', ' ')}.")

        return " ".join(parts)
    except Exception as e:
        logger.warning("Basic whisper build failed: %s", e)
        return "Incoming transfer. Lead details unavailable."


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post("/live-transfer")
async def initiate_live_transfer(
    body: InitiateTransferRequest,
    db: Session = Depends(get_db),
    current_user=Depends(current_user_flexible_dep),
):
    """
    Initiate a live transfer: hold caller → dial LO → whisper → bridge.
    """
    from database.models.live_transfer import LiveTransfer

    org_id = getattr(current_user, "organization_id", None)
    user_id = getattr(current_user, "id", None)

    # ── SEC-006: Tenant isolation — verify target LO belongs to same org ──
    lo = db.execute(text("""
        SELECT id, phone, first_name, last_name, organization_id FROM users
        WHERE id = :lo_id
    """), {"lo_id": body.target_lo_id}).fetchone()

    if not lo or not lo.phone:
        raise HTTPException(status_code=404, detail="Target LO not found or has no phone number")

    if lo.organization_id != org_id:
        logger.warning(
            "SEC-006 tenant isolation violation: user_id=%s org=%s tried to transfer to lo_id=%s org=%s",
            user_id, org_id, body.target_lo_id, lo.organization_id,
        )
        raise HTTPException(status_code=403, detail="Target LO does not belong to your organization")

    # ── DATA-007: Idempotency — check for existing active transfer on same call ──
    active_statuses = ("initiated", "lo_ringing", "lo_answered", "whisper_playing", "bridged")
    existing = db.query(LiveTransfer).filter(
        LiveTransfer.call_control_id == body.call_control_id,
        LiveTransfer.status.in_(active_statuses),
    ).first()

    if existing:
        logger.info(
            "DATA-007 idempotency: returning existing transfer %s (status=%s) for call_control_id=%s, "
            "org_id=%s, user_id=%s",
            existing.id, existing.status, body.call_control_id[:12], org_id, user_id,
        )
        lo_row = db.execute(text(
            "SELECT first_name, last_name FROM users WHERE id = :uid"
        ), {"uid": existing.lo_id}).fetchone()
        return {
            "transfer_id": existing.id,
            "status": existing.status,
            "lo_name": f"{lo_row.first_name} {lo_row.last_name}" if lo_row else None,
            "whisper_text": existing.whisper_text,
            "idempotent": True,
        }

    # ── OBS-010: Log transfer lifecycle — stage: initiated ──
    logger.info(
        "transfer_lifecycle stage=initiated call_control_id=%s lead_id=%s lo_id=%s "
        "transfer_type=%s org_id=%s user_id=%s",
        body.call_control_id[:12], body.lead_id, body.target_lo_id,
        body.transfer_type, org_id, user_id,
    )

    # Build whisper with cross-channel context
    whisper = _build_whisper(db, body.lead_id, body.whisper_text, organization_id=org_id)

    # Create transfer record
    transfer = LiveTransfer(
        organization_id=org_id,
        call_control_id=body.call_control_id,
        lo_id=body.target_lo_id,
        lo_phone=lo.phone,
        lead_id=body.lead_id,
        whisper_text=whisper,
        transfer_type=body.transfer_type,
        status="initiated",
    )
    db.add(transfer)
    db.commit()
    db.refresh(transfer)

    try:
        # Step 1 — hold the caller
        await _hold_call(body.call_control_id)
        logger.info(
            "transfer_lifecycle stage=caller_on_hold transfer_id=%s org_id=%s",
            transfer.id, org_id,
        )

        # Step 2 — dial the LO
        import base64
        client_state = base64.b64encode(transfer.id.encode()).decode()
        connection_id = os.getenv("TELNYX_CONNECTION_ID", "")
        from_number = os.getenv("TELNYX_FROM_NUMBER", "")

        dial_resp = await _dial(
            to=lo.phone,
            from_=from_number,
            connection_id=connection_id,
            client_state=client_state,
        )

        lo_call_data = dial_resp.get("data", {})
        transfer.lo_call_control_id = lo_call_data.get("call_control_id")
        transfer.status = "lo_ringing"
        db.commit()

        # OBS-010: Log transfer lifecycle — stage: lo_dialed
        logger.info(
            "transfer_lifecycle stage=lo_dialed transfer_id=%s lo_id=%s lo_call_control_id=%s org_id=%s",
            transfer.id, body.target_lo_id, transfer.lo_call_control_id, org_id,
        )

        return {
            "transfer_id": transfer.id,
            "status": "lo_ringing",
            "lo_name": f"{lo.first_name} {lo.last_name}",
            "whisper_text": whisper,
        }

    except Exception as e:
        logger.exception(
            "transfer_lifecycle stage=failed transfer_id=%s error=%s org_id=%s",
            transfer.id, e, org_id,
        )
        transfer.status = "failed"
        transfer.failure_reason = str(e)
        db.commit()
        raise HTTPException(status_code=502, detail="Failed to initiate transfer")


@router.post("/transfer-status")
async def transfer_status_webhook(request: Request, db: Session = Depends(get_db)):
    """
    Telnyx webhook for transfer call-leg events.
    Handles: call.answered, call.speak.ended, call.hangup
    """
    from database.models.live_transfer import LiveTransfer
    import base64

    payload = await request.json()
    event_data = payload.get("data", {})
    event_type = event_data.get("event_type", "")
    event_payload = event_data.get("payload", {})

    call_control_id = event_payload.get("call_control_id", "")
    client_state_b64 = event_payload.get("client_state", "")

    # Decode transfer ID from client_state
    transfer_id = None
    if client_state_b64:
        try:
            transfer_id = base64.b64decode(client_state_b64).decode()
        except Exception as e:
            logger.warning(
                "Failed to decode transfer client_state: %s (call_control_id=%s)",
                e, call_control_id[:12],
            )

    if not transfer_id:
        # Try lookup by LO call control id
        row = db.execute(text(
            "SELECT id FROM live_transfers WHERE lo_call_control_id = :ccid ORDER BY initiated_at DESC LIMIT 1"
        ), {"ccid": call_control_id}).fetchone()
        if row:
            transfer_id = row.id

    if not transfer_id:
        return JSONResponse({"status": "ignored"})

    transfer = db.query(LiveTransfer).filter_by(id=transfer_id).first()
    if not transfer:
        return JSONResponse({"status": "not_found"})

    now = datetime.now(timezone.utc)

    # ── LO answered → play whisper ──
    if event_type == "call.answered" and transfer.status == "lo_ringing":
        transfer.status = "lo_answered"
        transfer.lo_answered_at = now
        db.commit()

        # OBS-010: Log transfer lifecycle — stage: lo_answered
        logger.info(
            "transfer_lifecycle stage=lo_answered transfer_id=%s lo_id=%s org_id=%s",
            transfer_id, transfer.lo_id, transfer.organization_id,
        )

        try:
            transfer.status = "whisper_playing"
            db.commit()
            logger.info(
                "transfer_lifecycle stage=whisper_playing transfer_id=%s org_id=%s",
                transfer_id, transfer.organization_id,
            )
            await _speak(call_control_id, transfer.whisper_text)
        except Exception as e:
            logger.error(
                "transfer_lifecycle stage=whisper_failed transfer_id=%s error=%s org_id=%s",
                transfer_id, e, transfer.organization_id,
            )
            # Still try to bridge even if whisper fails
            transfer.status = "lo_answered"
            db.commit()

    # ── Whisper finished → bridge into conference ──
    elif event_type == "call.speak.ended" and transfer.status == "whisper_playing":
        transfer.whisper_completed_at = now
        db.commit()

        try:
            conf_name = f"transfer-{transfer.id[:8]}"
            conf_resp = await _create_conference(conf_name)
            conference_id = conf_resp.get("data", {}).get("id")
            transfer.conference_id = conference_id

            # Join both legs
            await _join_conference(conference_id, transfer.call_control_id)     # caller
            await _join_conference(conference_id, transfer.lo_call_control_id)  # LO

            # Unhold caller
            await _unhold_call(transfer.call_control_id)

            transfer.status = "bridged"
            transfer.bridged_at = now
            db.commit()

            # Cold transfer: AI leg drops immediately (nothing extra to do — we just don't join a third leg)
            # OBS-010: Log transfer lifecycle — stage: bridged
            logger.info(
                "transfer_lifecycle stage=bridged transfer_id=%s conference_id=%s "
                "lo_id=%s lead_id=%s org_id=%s",
                transfer_id, conference_id, transfer.lo_id,
                transfer.lead_id, transfer.organization_id,
            )

        except Exception as e:
            logger.exception(
                "transfer_lifecycle stage=bridge_failed transfer_id=%s error=%s org_id=%s",
                transfer_id, e, transfer.organization_id,
            )
            transfer.status = "failed"
            transfer.failure_reason = str(e)
            db.commit()

    # ── Call ended ──
    elif event_type == "call.hangup":
        if transfer.status in ("bridged", "lo_answered", "whisper_playing"):
            transfer.status = "completed"
            transfer.completed_at = now
            # OBS-010: Log transfer lifecycle — stage: completed
            logger.info(
                "transfer_lifecycle stage=completed transfer_id=%s lo_id=%s "
                "lead_id=%s org_id=%s",
                transfer_id, transfer.lo_id, transfer.lead_id, transfer.organization_id,
            )
        elif transfer.status == "lo_ringing":
            transfer.status = "failed"
            transfer.failure_reason = "LO did not answer"
            # OBS-010: Log transfer lifecycle — stage: failed (no answer)
            logger.warning(
                "transfer_lifecycle stage=failed_no_answer transfer_id=%s lo_id=%s org_id=%s",
                transfer_id, transfer.lo_id, transfer.organization_id,
            )
        db.commit()

    return JSONResponse({"status": "ok"})


@router.get("/live-transfer/{transfer_id}")
async def get_transfer_status(
    transfer_id: str,
    db: Session = Depends(get_db),
    current_user=Depends(current_user_flexible_dep),
):
    """Get current status of a live transfer."""
    from database.models.live_transfer import LiveTransfer

    org_id = getattr(current_user, "organization_id", None)
    transfer = db.query(LiveTransfer).filter_by(id=transfer_id, organization_id=org_id).first()

    if not transfer:
        raise HTTPException(status_code=404, detail="Transfer not found")

    lo = db.execute(text(
        "SELECT first_name, last_name FROM users WHERE id = :uid"
    ), {"uid": transfer.lo_id}).fetchone()

    return {
        "transfer_id": transfer.id,
        "status": transfer.status,
        "transfer_type": transfer.transfer_type,
        "lo_name": f"{lo.first_name} {lo.last_name}" if lo else None,
        "whisper_text": transfer.whisper_text,
        "initiated_at": transfer.initiated_at.isoformat() if transfer.initiated_at else None,
        "bridged_at": transfer.bridged_at.isoformat() if transfer.bridged_at else None,
        "completed_at": transfer.completed_at.isoformat() if transfer.completed_at else None,
        "failure_reason": transfer.failure_reason,
    }


@router.get("/live-transfers")
async def list_transfers(
    status: Optional[str] = None,
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user=Depends(current_user_flexible_dep),
):
    """List recent live transfers for the organization."""
    from database.models.live_transfer import LiveTransfer

    org_id = getattr(current_user, "organization_id", None)
    q = db.query(LiveTransfer).filter_by(organization_id=org_id)

    if status:
        q = q.filter_by(status=status)

    transfers = q.order_by(LiveTransfer.initiated_at.desc()).limit(limit).all()

    results = []
    for t in transfers:
        lo = db.execute(text(
            "SELECT first_name, last_name FROM users WHERE id = :uid"
        ), {"uid": t.lo_id}).fetchone()
        results.append({
            "transfer_id": t.id,
            "status": t.status,
            "lo_name": f"{lo.first_name} {lo.last_name}" if lo else None,
            "caller_phone": t.caller_phone,
            "transfer_type": t.transfer_type,
            "initiated_at": t.initiated_at.isoformat() if t.initiated_at else None,
        })

    return {"transfers": results, "count": len(results)}
