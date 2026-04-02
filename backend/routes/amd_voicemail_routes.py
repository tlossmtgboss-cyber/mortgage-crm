"""
AMD Voicemail Routes — Answering Machine Detection → Slybroadcast auto-drop

When an outbound call hits an answering machine (AMD) or goes unanswered,
automatically trigger a Slybroadcast ringless voicemail drop.

Telnyx AMD webhook sends JSON with result: "human", "machine", "not_sure", "fax"
Telnyx call status sends: "answered", "no-answer", "busy", "failed"
"""

import os
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import text
import httpx

from db import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/telephony", tags=["AMD Voicemail"])

# Slybroadcast credentials
SLYBROADCAST_URL = "https://www.mobile-sphere.com/gateway/vmb.php"


# ---------------------------------------------------------------------------
# Per-org AMD config (stored in org_amd_configs table)
# ---------------------------------------------------------------------------

class AMDConfig(BaseModel):
    amd_enabled: bool = True
    amd_action: str = "drop_voicemail"  # drop_voicemail | hangup | ignore
    default_vm_audio_url: str = ""
    ring_timeout_seconds: int = 25
    caller_id: str = ""


def _get_org_amd_config(db: Session, organization_id: int) -> AMDConfig:
    """Load AMD config for org, or return defaults."""
    row = db.execute(text("""
        SELECT amd_enabled, amd_action, default_vm_audio_url,
               ring_timeout_seconds, caller_id
        FROM org_amd_configs
        WHERE organization_id = :org_id
    """), {"org_id": organization_id}).fetchone()

    if not row:
        return AMDConfig()

    return AMDConfig(
        amd_enabled=row.amd_enabled if row.amd_enabled is not None else True,
        amd_action=row.amd_action or "drop_voicemail",
        default_vm_audio_url=row.default_vm_audio_url or "",
        ring_timeout_seconds=row.ring_timeout_seconds or 25,
        caller_id=row.caller_id or "",
    )


# ---------------------------------------------------------------------------
# Slybroadcast helper (mirrors pattern from voicemail_drop_routes.py)
# ---------------------------------------------------------------------------

async def trigger_slybroadcast_drop(
    phone_number: str,
    audio_url: str,
    caller_id: str = "",
    organization_id: Optional[int] = None,
) -> dict:
    """
    Fire a Slybroadcast ringless voicemail to a single phone number.
    Returns {"success": True, "session_id": "..."} on success.
    """
    sb_email = os.getenv("SLYBROADCAST_EMAIL", "")
    sb_password = os.getenv("SLYBROADCAST_PASSWORD", "")

    if not sb_email or not sb_password:
        logger.error("Slybroadcast credentials not configured")
        return {"success": False, "error": "Slybroadcast not configured"}

    if not audio_url:
        logger.error("No audio URL for voicemail drop to %s", phone_number[-4:])
        return {"success": False, "error": "No audio URL"}

    # Normalize phone: strip + and ensure 11-digit US format
    clean_number = phone_number.replace("+", "").replace("-", "").replace(" ", "")
    if len(clean_number) == 10:
        clean_number = f"1{clean_number}"

    # Caller ID: 10 digits, no country code
    clean_caller = (caller_id or os.getenv("TELNYX_FROM_NUMBER", "")).replace("+", "")
    if len(clean_caller) == 11 and clean_caller.startswith("1"):
        clean_caller = clean_caller[1:]

    # Webhook URL for delivery status
    base_url = os.getenv("API_BASE_URL", os.getenv("RAILWAY_PUBLIC_DOMAIN", ""))
    if base_url and not base_url.startswith("http"):
        base_url = f"https://{base_url}"
    dispo_url = f"{base_url}/api/v1/voicemail/webhook/rvm" if base_url else ""

    payload = {
        "c_uid": sb_email,
        "c_password": sb_password,
        "c_callerID": clean_caller,
        "c_phone": clean_number,
        "c_url": audio_url,
        "c_date": "now",
        "c_audio": "mp3",
        "mobile_only": "1",
    }
    if dispo_url:
        payload["c_dispo_url"] = dispo_url

    logger.info("Slybroadcast AMD drop: phone=***%s audio=%s", clean_number[-4:], audio_url[:80])

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(SLYBROADCAST_URL, data=payload)

        if response.status_code != 200:
            logger.error("Slybroadcast HTTP %s: %s", response.status_code, response.text[:300])
            return {"success": False, "error": f"HTTP {response.status_code}"}

        body = response.text.strip()
        lines = [ln.strip() for ln in body.splitlines() if ln.strip()]

        if not lines or lines[0].upper() != "OK":
            logger.error("Slybroadcast error: %s", body[:300])
            return {"success": False, "error": body[:300]}

        raw_session = lines[1] if len(lines) > 1 else ""
        session_id = raw_session.split("=", 1)[-1].strip() if "=" in raw_session else raw_session

        logger.info("Slybroadcast RVM queued: session_id=%s phone=***%s", session_id, clean_number[-4:])
        return {"success": True, "session_id": session_id, "provider": "slybroadcast"}

    except Exception as e:
        logger.exception("Slybroadcast drop failed for ***%s", clean_number[-4:])
        return {"success": False, "error": str(e)}


# ---------------------------------------------------------------------------
# Log AMD events
# ---------------------------------------------------------------------------

def _log_amd_event(db: Session, phone: str, event_type: str, result: str, org_id: Optional[int], meta: dict):
    """Insert an AMD event into the amd_events log table (best-effort)."""
    try:
        db.execute(text("""
            INSERT INTO amd_events (phone, event_type, result, organization_id, meta, created_at)
            VALUES (:phone, :event_type, :result, :org_id, :meta, :now)
        """), {
            "phone": phone,
            "event_type": event_type,
            "result": result,
            "org_id": org_id,
            "meta": str(meta)[:2000],
            "now": datetime.now(timezone.utc),
        })
        db.commit()
    except Exception as e:
        logger.debug("Could not log AMD event (table may not exist yet): %s", e)
        db.rollback()


# ---------------------------------------------------------------------------
# Webhook: Telnyx AMD result
# ---------------------------------------------------------------------------

@router.post("/amd-callback")
async def amd_callback(request: Request, db: Session = Depends(get_db)):
    """
    Telnyx AMD (Answering Machine Detection) webhook.

    When Telnyx determines whether a human or machine answered:
      - machine → trigger Slybroadcast voicemail drop
      - human   → do nothing (call proceeds normally)
      - fax     → hang up
    """
    payload = await request.json()
    event_data = payload.get("data", {})
    event_payload = event_data.get("payload", {})

    amd_result = event_payload.get("result", "")  # human, machine, not_sure, fax
    call_control_id = event_payload.get("call_control_id", "")
    to_number = event_payload.get("to", "")
    from_number = event_payload.get("from", "")

    logger.info("AMD callback: result=%s to=%s call=%s", amd_result, to_number[-4:] if to_number else "?", call_control_id[:12])

    # Try to resolve organization from the call
    org_id = None
    call_row = db.execute(text("""
        SELECT organization_id FROM call_logs WHERE call_sid = :sid ORDER BY created_at DESC LIMIT 1
    """), {"sid": call_control_id}).fetchone()
    if call_row:
        org_id = call_row.organization_id

    _log_amd_event(db, to_number, "amd_detection", amd_result, org_id, {
        "call_control_id": call_control_id,
        "from": from_number,
    })

    if amd_result == "machine":
        # Load org config
        config = _get_org_amd_config(db, org_id) if org_id else AMDConfig()

        if not config.amd_enabled or config.amd_action != "drop_voicemail":
            logger.info("AMD action=%s for org %s — skipping drop", config.amd_action, org_id)
            return JSONResponse({"status": "skipped", "reason": config.amd_action})

        # Hang up the Telnyx call leg first
        try:
            telnyx_key = os.getenv("TELNYX_API_KEY", "")
            async with httpx.AsyncClient(timeout=10) as client:
                await client.post(
                    f"https://api.telnyx.com/v2/calls/{call_control_id}/actions/hangup",
                    headers={"Authorization": f"Bearer {telnyx_key}"},
                    json={},
                )
        except Exception as e:
            logger.warning("Could not hang up call %s: %s", call_control_id[:12], e)

        # TCPA quiet hours check — block voicemail drops outside 8am-9pm
        try:
            from routes.voicemail_drop_routes import check_calling_hours
            tcpa_ok = check_calling_hours(to_number)
            if not tcpa_ok:
                _log_amd_event(db, to_number, "tcpa_blocked", "quiet_hours", org_id, {})
                logger.info("AMD voicemail drop blocked by TCPA quiet hours for ***%s", to_number[-4:])
                return JSONResponse({"status": "tcpa_blocked"})
        except ImportError:
            pass  # If check unavailable, proceed (calls were already placed)

        # Trigger Slybroadcast drop
        result = await trigger_slybroadcast_drop(
            phone_number=to_number,
            audio_url=config.default_vm_audio_url,
            caller_id=config.caller_id or from_number,
            organization_id=org_id,
        )

        _log_amd_event(db, to_number, "slybroadcast_triggered", "success" if result.get("success") else "failed", org_id, result)

        return JSONResponse({"status": "voicemail_dropped", "slybroadcast": result})

    elif amd_result == "fax":
        # Hang up on fax machines
        try:
            telnyx_key = os.getenv("TELNYX_API_KEY", "")
            async with httpx.AsyncClient(timeout=10) as client:
                await client.post(
                    f"https://api.telnyx.com/v2/calls/{call_control_id}/actions/hangup",
                    headers={"Authorization": f"Bearer {telnyx_key}"},
                    json={},
                )
        except Exception:
            pass
        return JSONResponse({"status": "fax_hangup"})

    # human or not_sure → call proceeds normally
    return JSONResponse({"status": "human_detected"})


# ---------------------------------------------------------------------------
# Webhook: Telnyx call status (no-answer / busy → auto voicemail drop)
# ---------------------------------------------------------------------------

@router.post("/call-noanswer-callback")
async def call_noanswer_callback(request: Request, db: Session = Depends(get_db)):
    """
    Telnyx call status webhook for no-answer / busy scenarios.

    When a call is not answered or line is busy, automatically queue
    a Slybroadcast voicemail drop to that number.
    """
    payload = await request.json()
    event_data = payload.get("data", {})
    event_type = event_data.get("event_type", "")
    event_payload = event_data.get("payload", {})

    # We only care about call.hangup with specific hangup causes
    if event_type != "call.hangup":
        return JSONResponse({"status": "ignored"})

    hangup_cause = event_payload.get("hangup_cause", "")
    sip_cause = event_payload.get("sip_hangup_cause", "")
    to_number = event_payload.get("to", "")
    from_number = event_payload.get("from", "")
    call_control_id = event_payload.get("call_control_id", "")

    # no-answer: hangup_cause=timeout or normal_clearing with short duration
    # busy: hangup_cause=user_busy
    no_answer_causes = {"timeout", "no_answer", "originator_cancel"}
    busy_causes = {"user_busy", "busy"}

    trigger = hangup_cause in no_answer_causes or hangup_cause in busy_causes

    if not trigger:
        return JSONResponse({"status": "ignored", "cause": hangup_cause})

    logger.info("Call no-answer/busy: cause=%s to=%s", hangup_cause, to_number[-4:] if to_number else "?")

    # Resolve org
    org_id = None
    call_row = db.execute(text("""
        SELECT organization_id FROM call_logs WHERE call_sid = :sid ORDER BY created_at DESC LIMIT 1
    """), {"sid": call_control_id}).fetchone()
    if call_row:
        org_id = call_row.organization_id

    _log_amd_event(db, to_number, "no_answer", hangup_cause, org_id, {
        "sip_cause": sip_cause,
        "call_control_id": call_control_id,
    })

    config = _get_org_amd_config(db, org_id) if org_id else AMDConfig()

    if not config.amd_enabled or config.amd_action != "drop_voicemail":
        return JSONResponse({"status": "skipped"})

    if not config.default_vm_audio_url:
        logger.warning("No default VM audio URL for org %s — skipping auto-drop", org_id)
        return JSONResponse({"status": "skipped", "reason": "no_audio_url"})

    # TCPA quiet hours check
    try:
        from routes.voicemail_drop_routes import check_calling_hours
        if not check_calling_hours(to_number):
            _log_amd_event(db, to_number, "tcpa_blocked", "quiet_hours", org_id, {})
            return JSONResponse({"status": "tcpa_blocked"})
    except ImportError:
        pass

    result = await trigger_slybroadcast_drop(
        phone_number=to_number,
        audio_url=config.default_vm_audio_url,
        caller_id=config.caller_id or from_number,
        organization_id=org_id,
    )

    _log_amd_event(db, to_number, "noanswer_slybroadcast", "success" if result.get("success") else "failed", org_id, result)

    return JSONResponse({"status": "voicemail_dropped", "slybroadcast": result})


# ---------------------------------------------------------------------------
# Admin: Get/Set AMD config per org
# ---------------------------------------------------------------------------

@router.get("/amd-config")
async def get_amd_config(
    db: Session = Depends(get_db),
    current_user=Depends(lambda: None),  # Will be wired to real auth at registration
):
    """Get AMD configuration for the current org."""
    from routes.auth_deps import current_user_flexible_dep
    # Placeholder — real auth injected at router registration
    org_id = getattr(current_user, "organization_id", None) if current_user else None
    if not org_id:
        raise HTTPException(status_code=401, detail="Authentication required")

    config = _get_org_amd_config(db, org_id)
    return config.dict()


@router.put("/amd-config")
async def update_amd_config(
    body: AMDConfig,
    db: Session = Depends(get_db),
    current_user=Depends(lambda: None),
):
    """Update AMD configuration for the current org."""
    org_id = getattr(current_user, "organization_id", None) if current_user else None
    if not org_id:
        raise HTTPException(status_code=401, detail="Authentication required")

    # Upsert
    existing = db.execute(text(
        "SELECT id FROM org_amd_configs WHERE organization_id = :org_id"
    ), {"org_id": org_id}).fetchone()

    if existing:
        db.execute(text("""
            UPDATE org_amd_configs SET
                amd_enabled = :enabled, amd_action = :action,
                default_vm_audio_url = :audio, ring_timeout_seconds = :timeout,
                caller_id = :cid, updated_at = :now
            WHERE organization_id = :org_id
        """), {
            "enabled": body.amd_enabled, "action": body.amd_action,
            "audio": body.default_vm_audio_url, "timeout": body.ring_timeout_seconds,
            "cid": body.caller_id, "now": datetime.now(timezone.utc), "org_id": org_id,
        })
    else:
        db.execute(text("""
            INSERT INTO org_amd_configs (organization_id, amd_enabled, amd_action,
                default_vm_audio_url, ring_timeout_seconds, caller_id, created_at, updated_at)
            VALUES (:org_id, :enabled, :action, :audio, :timeout, :cid, :now, :now)
        """), {
            "org_id": org_id, "enabled": body.amd_enabled, "action": body.amd_action,
            "audio": body.default_vm_audio_url, "timeout": body.ring_timeout_seconds,
            "cid": body.caller_id, "now": datetime.now(timezone.utc),
        })

    db.commit()
    return {"status": "updated"}
