"""
Internal API endpoints for Aria call management.
Warm transfer, voicemail drop, call logging, outbound initiation.
"""
import os
import logging
import asyncio
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db

logger = logging.getLogger("aria.internal.calls")

router = APIRouter(prefix="/internal/aria", tags=["Aria Internal Calls"])

INTERNAL_API_KEY = os.environ.get("INTERNAL_API_KEY", "")
TELNYX_API_KEY = os.environ.get("TELNYX_API_KEY", "")
TELNYX_PHONE_NUMBER = os.environ.get("TELNYX_PHONE_NUMBER", "")
TELNYX_CONNECTION_ID = os.environ.get("TELNYX_CONNECTION_ID", "")


def _verify_internal_key(request: Request):
    key = request.headers.get("X-Internal-API-Key", "")
    if not INTERNAL_API_KEY or key != INTERNAL_API_KEY:
        raise HTTPException(status_code=403, detail="Invalid internal API key")


# --- Schemas ----------------------------------------------------------------

class InitiateOutboundRequest(BaseModel):
    to_phone: str
    lead_id: Optional[int] = None
    intent: str = "general"
    authorization_type: str = "lo_manual"
    authorized_by: Optional[int] = None
    rule_id: Optional[str] = None


class LogCallRequest(BaseModel):
    lead_id: Optional[int] = None
    user_id: Optional[int] = None
    organization_id: Optional[int] = None
    direction: str = "inbound"
    duration_seconds: Optional[int] = None
    summary: Optional[str] = None
    outcome: Optional[str] = None
    transcript: Optional[list] = None
    tools_executed: Optional[list] = None
    livekit_room_name: Optional[str] = None


class VoicemailDropRequest(BaseModel):
    lead_id: int
    intent: str
    template_context: dict = {}


# --- Endpoints ---------------------------------------------------------------

@router.post("/call/initiate-outbound")
async def initiate_outbound_call(
    req: InitiateOutboundRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """Initiate an outbound call via Telnyx, bridging into a LiveKit room."""
    _verify_internal_key(request)

    from integrations.sms_service import _to_e164
    normalized = _to_e164(req.to_phone)
    if not normalized:
        return {"success": False, "error": f"Invalid phone: {req.to_phone}"}

    # Record TCPA authorization
    try:
        from database.models.call_authorization import CallAuthorization
        auth_record = CallAuthorization(
            lead_id=req.lead_id or 0,
            authorization_type=req.authorization_type,
            authorized_by=req.authorized_by,
            rule_id=req.rule_id,
        )
        db.add(auth_record)
        db.flush()
    except Exception as e:
        logger.error(f"Failed to record call authorization: {e}")

    # Place call via Telnyx Call Control API
    from agents.aria_config import OUTBOUND_CALL_CONFIG
    import requests

    try:
        payload = {
            "to": normalized,
            "from": TELNYX_PHONE_NUMBER,
            "connection_id": TELNYX_CONNECTION_ID,
            "answering_machine_detection": OUTBOUND_CALL_CONFIG["answering_machine_detection"],
            "answering_machine_detection_config": OUTBOUND_CALL_CONFIG["answering_machine_detection_config"],
            "timeout_secs": OUTBOUND_CALL_CONFIG["timeout_secs"],
            "webhook_url": f"{os.getenv('API_URL', 'https://api.perenniaai.com')}/api/v1/telnyx/webhook",
        }

        resp = requests.post(
            "https://api.telnyx.com/v2/calls",
            headers={
                "Authorization": f"Bearer {TELNYX_API_KEY}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=10,
        )

        if resp.status_code in (200, 201):
            data = resp.json()
            call_control_id = data.get("data", {}).get("call_control_id")
            return {"success": True, "call_control_id": call_control_id}
        else:
            logger.error(f"Telnyx call initiation failed: {resp.status_code} {resp.text[:200]}")
            return {"success": False, "error": "Failed to initiate call"}
    except Exception as e:
        logger.error(f"Outbound call error: {e}")
        return {"success": False, "error": str(e)}


@router.post("/call/log")
async def log_call(
    req: LogCallRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """Log a completed call session to the database."""
    _verify_internal_key(request)

    try:
        from database.models.voice_call_session import VoiceCallSession

        session = VoiceCallSession(
            session_uuid=str(uuid.uuid4()),
            organization_id=req.organization_id,
            user_id=req.user_id or 0,
            lead_id=req.lead_id,
            direction=req.direction,
            status="completed",
            duration_seconds=req.duration_seconds,
            summary=req.summary,
            outcome=req.outcome,
            transcript=req.transcript or [],
            tools_executed=req.tools_executed or [],
        )
        db.add(session)
        db.commit()
        return {"success": True, "session_id": session.id}
    except Exception as e:
        logger.error(f"Failed to log call: {e}")
        db.rollback()
        return {"success": False, "error": str(e)}


@router.post("/call/voicemail-drop")
async def voicemail_drop(
    req: VoicemailDropRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """Record a voicemail drop and send paired SMS."""
    _verify_internal_key(request)

    from agents.aria_config import render_voicemail_template

    message = render_voicemail_template(req.intent, req.template_context)
    if not message:
        return {"success": False, "error": f"Unknown voicemail template: {req.intent}"}

    # Send paired SMS (non-blocking)
    try:
        from integrations.sms_service import SMSClient
        sms_client = SMSClient(db)
        phone = req.template_context.get("phone", "")
        if phone:
            asyncio.create_task(
                sms_client.send_sms(
                    to_phone=phone,
                    message=message,
                    lead_id=req.lead_id,
                    bypass_compliance=False,
                )
            )
    except Exception as e:
        logger.warning(f"Paired SMS failed: {e}")

    return {"success": True, "voicemail_text": message}
