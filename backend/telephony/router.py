"""Dialer API endpoints initialization"""

from fastapi import APIRouter, Depends, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session
from typing import Optional, List
from datetime import datetime
import logging

from .provider import get_telephony_provider
from .dialer_engine import DialerEngine, click_to_dial
from .compliance import ComplianceChecker
from .websocket import ws_manager
from .schemas import (
    AgentTelephonySettingsUpdate,
    ClickToDialRequest,
    ClickToDialResponse,
    StartSessionRequest,
    StartSessionResponse,
    SessionStatusResponse,
    DispositionRequest,
    DispositionResponse,
    VerifyCallerIdRequest,
    VerifyCallerIdResponse,
    ComplianceCheckResponse,
    CallLogEntry,
    CallLogsResponse,
)

logger = logging.getLogger(__name__)

# Create router
router = APIRouter(prefix="/api/v1/dialer", tags=["dialer"])


# =============================================================================
# Dependency to get database session (to be injected from main app)
# =============================================================================

# Dependency functions - these get replaced by main app via set_dependencies()
def get_db():
    """Database session dependency - replaced by main app"""
    raise RuntimeError("get_db not initialized - call set_dependencies() first")


def get_current_user():
    """User dependency - replaced by main app"""
    raise RuntimeError("get_current_user not initialized - call set_dependencies() first")


def set_dependencies(db_dependency, user_dependency):
    """
    Replace the placeholder dependency functions with real ones from main app.
    This must be called during app initialization before any routes are accessed.
    """
    global get_db, get_current_user
    get_db = db_dependency
    get_current_user = user_dependency


# =============================================================================
# Agent Settings Endpoints
# =============================================================================

@router.get("/settings")
async def get_dialer_settings(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Get agent's telephony/dialer settings"""
    # Import models from main
    from main import AgentTelephonySettings, VerifiedCallerId

    settings = db.query(AgentTelephonySettings).filter(
        AgentTelephonySettings.user_id == current_user.id
    ).first()

    if not settings:
        # Create default settings
        settings = AgentTelephonySettings(
            user_id=current_user.id,
            dialer_enabled=True,
            max_calls_per_day=100,
            auto_advance=True,
            pause_between_calls=3
        )
        db.add(settings)
        db.commit()
        db.refresh(settings)

    # Get verified caller IDs
    caller_ids = db.query(VerifiedCallerId).filter(
        VerifiedCallerId.user_id == current_user.id,
        VerifiedCallerId.verification_status == "verified"
    ).all()

    return {
        "user_id": settings.user_id,
        "cell_phone": settings.cell_phone,
        "business_caller_id": settings.business_caller_id,
        "dialer_enabled": settings.dialer_enabled,
        "max_calls_per_day": settings.max_calls_per_day,
        "auto_advance": settings.auto_advance,
        "pause_between_calls": settings.pause_between_calls,
        "verified_caller_ids": [
            {"phone": c.phone_number, "name": c.friendly_name, "is_default": c.phone_number == settings.business_caller_id}
            for c in caller_ids
        ]
    }


@router.put("/settings")
async def update_dialer_settings(
    settings_update: AgentTelephonySettingsUpdate,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Update agent's telephony/dialer settings"""
    from main import AgentTelephonySettings

    settings = db.query(AgentTelephonySettings).filter(
        AgentTelephonySettings.user_id == current_user.id
    ).first()

    if not settings:
        settings = AgentTelephonySettings(user_id=current_user.id)
        db.add(settings)

    # Update fields that were provided
    update_data = settings_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        if value is not None:
            setattr(settings, field, value)

    settings.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(settings)

    return {"success": True, "message": "Settings updated"}


# =============================================================================
# Caller ID Verification
# =============================================================================

@router.post("/verify-caller-id")
async def verify_caller_id(
    request: VerifyCallerIdRequest,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Start caller ID verification process"""
    from main import VerifiedCallerId

    provider = get_telephony_provider()
    result = provider.verify_caller_id(request.phone_number, request.friendly_name)

    if result.get("success"):
        # Save pending verification
        caller_id = VerifiedCallerId(
            user_id=current_user.id,
            phone_number=request.phone_number,
            friendly_name=request.friendly_name,
            twilio_sid=result.get("call_sid"),
            verification_status="pending"
        )
        db.add(caller_id)
        db.commit()

    return result


@router.get("/verified-caller-ids")
async def list_verified_caller_ids(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """List all verified caller IDs for the agent"""
    from main import VerifiedCallerId

    caller_ids = db.query(VerifiedCallerId).filter(
        VerifiedCallerId.user_id == current_user.id
    ).all()

    return {"caller_ids": caller_ids}


# =============================================================================
# Click-to-Dial
# =============================================================================

@router.post("/click-to-dial", response_model=ClickToDialResponse)
async def api_click_to_dial(
    request: ClickToDialRequest,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Initiate a single click-to-dial call"""
    import os
    base_url = os.getenv("BASE_URL", "https://mortgage-crm-production-7a9a.up.railway.app")

    result = click_to_dial(
        db_session=db,
        agent_id=current_user.id,
        phone_number=request.phone_number,
        contact_name=request.contact_name,
        base_url=base_url,
        lead_id=request.lead_id,
        loan_id=request.loan_id,
        task_id=request.task_id
    )

    return ClickToDialResponse(
        success=result.get("success", False),
        call_sid=result.get("call_sid"),
        contact_name=request.contact_name,
        contact_phone=request.phone_number,
        error=result.get("error")
    )


# =============================================================================
# Dialer Sessions
# =============================================================================

@router.post("/sessions", response_model=StartSessionResponse)
async def create_dialer_session(
    request: StartSessionRequest,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Create a new power dialer session"""
    import os
    base_url = os.getenv("BASE_URL", "https://mortgage-crm-production-7a9a.up.railway.app")

    engine = DialerEngine(db, current_user.id)
    result = engine.create_session(request.task_ids, base_url)

    return StartSessionResponse(
        success=result.get("success", False),
        session_id=result.get("session_id"),
        status=result.get("status"),
        total_tasks=result.get("total_tasks", 0),
        error=result.get("error")
    )


@router.get("/sessions/active")
async def get_active_session(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Get the agent's currently active dialer session"""
    from main import DialerSession, DialerSessionStatus

    session = db.query(DialerSession).filter(
        DialerSession.agent_id == current_user.id,
        DialerSession.status == DialerSessionStatus.ACTIVE
    ).first()

    if not session:
        return {"active_session": None}

    engine = DialerEngine(db, current_user.id)
    return {"active_session": engine.get_session_status(session.id)}


@router.get("/sessions/{session_id}", response_model=SessionStatusResponse)
async def get_session_status(
    session_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Get status of a specific dialer session"""
    engine = DialerEngine(db, current_user.id)
    status = engine.get_session_status(session_id)

    if not status:
        raise HTTPException(status_code=404, detail="Session not found")

    return status


@router.get("/sessions/{session_id}/next-task")
async def get_next_task(
    session_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Get the next pending task in a session"""
    engine = DialerEngine(db, current_user.id)
    task = engine.get_next_task(session_id)

    if not task:
        return {"next_task": None, "message": "No more pending tasks"}

    return {"next_task": task}


@router.post("/sessions/{session_id}/call/{task_id}")
async def initiate_session_call(
    session_id: int,
    task_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Initiate a call for a specific task in the session"""
    import os
    base_url = os.getenv("BASE_URL", "https://mortgage-crm-production-7a9a.up.railway.app")

    engine = DialerEngine(db, current_user.id)
    result = engine.initiate_call(session_id, task_id, base_url)

    if not result.get("success"):
        raise HTTPException(
            status_code=400,
            detail=result.get("error", "Failed to initiate call")
        )

    return result


@router.post("/sessions/{session_id}/tasks/{task_id}/disposition", response_model=DispositionResponse)
async def set_task_disposition(
    session_id: int,
    task_id: int,
    request: DispositionRequest,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Set disposition for a completed call"""
    engine = DialerEngine(db, current_user.id)
    result = engine.set_disposition(
        session_id=session_id,
        task_id=task_id,
        disposition=request.disposition,
        notes=request.notes,
        schedule_callback=request.schedule_callback
    )

    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error"))

    return DispositionResponse(
        success=True,
        task_id=task_id,
        disposition=request.disposition
    )


@router.post("/sessions/{session_id}/tasks/{task_id}/skip")
async def skip_session_task(
    session_id: int,
    task_id: int,
    reason: str = "manual_skip",
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Skip a task in the session"""
    engine = DialerEngine(db, current_user.id)
    result = engine.skip_task(session_id, task_id, reason)

    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error"))

    return result


@router.post("/sessions/{session_id}/pause")
async def pause_session(
    session_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Pause an active dialer session"""
    engine = DialerEngine(db, current_user.id)
    result = engine.pause_session(session_id)

    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error"))

    return result


@router.post("/sessions/{session_id}/resume")
async def resume_session(
    session_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Resume a paused dialer session"""
    engine = DialerEngine(db, current_user.id)
    result = engine.resume_session(session_id)

    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error"))

    return result


@router.post("/sessions/{session_id}/stop")
async def stop_session(
    session_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Stop a dialer session completely"""
    engine = DialerEngine(db, current_user.id)
    result = engine.stop_session(session_id)

    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error"))

    return result


# =============================================================================
# Compliance Endpoints
# =============================================================================

@router.get("/compliance/check", response_model=ComplianceCheckResponse)
async def check_compliance(
    phone_number: str = Query(...),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Run compliance checks for a phone number"""
    compliance = ComplianceChecker(db)
    result = compliance.full_compliance_check(phone_number, current_user.id)

    return ComplianceCheckResponse(**result)


@router.post("/dnc/add")
async def add_to_dnc(
    phone_number: str,
    reason: str = "customer_request",
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Add a phone number to the Do Not Call list"""
    compliance = ComplianceChecker(db)
    success = compliance.add_to_dnc(phone_number, reason, current_user.id)

    if not success:
        raise HTTPException(status_code=500, detail="Failed to add to DNC list")

    return {"success": True, "message": f"Added {phone_number} to DNC list"}


@router.delete("/dnc/{phone_number}")
async def remove_from_dnc(
    phone_number: str,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Remove a phone number from the Do Not Call list"""
    compliance = ComplianceChecker(db)
    success = compliance.remove_from_dnc(phone_number)

    return {"success": success, "message": "Removed from DNC list" if success else "Number not found on DNC list"}


# =============================================================================
# Call Logs
# =============================================================================

@router.get("/call-logs", response_model=CallLogsResponse)
async def get_call_logs(
    skip: int = 0,
    limit: int = 50,
    lead_id: Optional[int] = None,
    loan_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Get call history for the agent"""
    from main import CallLog

    query = db.query(CallLog).filter(CallLog.agent_id == current_user.id)

    if lead_id:
        query = query.filter(CallLog.lead_id == lead_id)
    if loan_id:
        query = query.filter(CallLog.loan_id == loan_id)

    total = query.count()
    logs = query.order_by(CallLog.created_at.desc()).offset(skip).limit(limit).all()

    return CallLogsResponse(
        call_logs=[CallLogEntry.model_validate(log) for log in logs],
        total=total
    )


# =============================================================================
# WebSocket Endpoint
# =============================================================================

@router.websocket("/ws/{agent_id}")
async def websocket_dialer(websocket: WebSocket, agent_id: str):
    """
    WebSocket connection for real-time dialer updates

    Clients should connect with their agent_id to receive:
    - Call status updates (ringing, answered, completed)
    - Session progress updates
    - Disposition prompts
    - Error notifications
    """
    await ws_manager.connect(websocket, agent_id)
    try:
        while True:
            # Keep connection alive, handle incoming messages if needed
            data = await websocket.receive_text()
            # Echo back acknowledgment
            await websocket.send_json({"type": "ack", "message": data})
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket, agent_id)
        logger.info(f"WebSocket disconnected for agent {agent_id}")
    except Exception as e:
        logger.error(f"WebSocket error for agent {agent_id}: {e}")
        ws_manager.disconnect(websocket, agent_id)


@router.get("/ws/status")
async def websocket_status():
    """Get WebSocket connection status for monitoring"""
    return {
        "connected_agents": ws_manager.get_connected_agents(),
        "total_connections": sum(len(conns) for conns in ws_manager.active_connections.values())
    }


# =============================================================================
# Twilio Webhook Endpoints (TwiML)
# =============================================================================

from fastapi.responses import Response

@router.post("/twiml/click-to-dial")
@router.get("/twiml/click-to-dial")
async def twiml_click_to_dial(
    request: Request,
    destination: Optional[str] = None,
    contact_name: Optional[str] = None
):
    """
    TwiML endpoint for click-to-dial calls.

    When Twilio connects to the agent's phone, this tells Twilio to:
    1. Say a brief message with contact name
    2. Dial the destination number (the contact)

    The flow is:
    - Twilio calls agent's cell phone
    - Agent answers
    - This TwiML plays and dials the contact
    - Agent and contact are bridged together
    """
    # Get form data from Twilio
    form_data = await request.form()
    from_number = form_data.get("From", "")  # The Twilio number (caller ID)

    logger.info(f"TwiML click-to-dial: destination={destination}, contact={contact_name}, from={from_number}")

    if not destination:
        # Fallback error
        twiml = """<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say voice="alice">Sorry, no destination number was provided.</Say>
    <Hangup/>
</Response>"""
        return Response(content=twiml, media_type="application/xml")

    # Announce the contact name if provided
    announcement = f"Connecting you to {contact_name}." if contact_name else "Connecting your call."

    twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say voice="alice">{announcement}</Say>
    <Dial callerId="{from_number}" timeout="30">
        <Number>{destination}</Number>
    </Dial>
</Response>"""

    return Response(content=twiml, media_type="application/xml")


@router.post("/twiml/outbound")
@router.get("/twiml/outbound")
async def twiml_outbound(
    request: Request,
    session_id: Optional[int] = None,
    task_id: Optional[int] = None
):
    """
    TwiML endpoint for power dialer outbound calls.

    Similar to click-to-dial but includes session tracking.
    """
    form_data = await request.form()
    to_number = form_data.get("To", "")
    from_number = form_data.get("From", "")

    logger.info(f"TwiML outbound: session={session_id}, task={task_id}, To={to_number}")

    twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say voice="alice">Connecting your call.</Say>
    <Dial callerId="{from_number}" timeout="30" action="/api/v1/dialer/webhook/dial-status?session_id={session_id}&amp;task_id={task_id}">
        <Number>{to_number}</Number>
    </Dial>
</Response>"""

    return Response(content=twiml, media_type="application/xml")


@router.post("/webhook/click-to-dial-status")
async def webhook_click_to_dial_status(
    request: Request,
    agent_id: Optional[int] = None
):
    """
    Status callback for click-to-dial calls.

    Twilio calls this when the call status changes (ringing, answered, completed, etc.)
    """
    form_data = await request.form()
    call_sid = form_data.get("CallSid", "")
    call_status = form_data.get("CallStatus", "")
    duration = form_data.get("CallDuration", "0")

    logger.info(f"Click-to-dial status: agent={agent_id}, sid={call_sid}, status={call_status}, duration={duration}")

    # Send WebSocket notification if agent is connected
    if agent_id:
        try:
            await ws_manager.send_to_agent(str(agent_id), {
                "type": "call_status",
                "call_sid": call_sid,
                "status": call_status,
                "duration": int(duration) if duration else 0
            })
        except Exception as e:
            logger.error(f"WebSocket notification error: {e}")

    return {"success": True}


@router.post("/webhook/status")
async def webhook_call_status(
    request: Request,
    session_id: Optional[int] = None,
    task_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Status callback for power dialer session calls.

    Updates session state based on call progress.
    """
    form_data = await request.form()
    call_sid = form_data.get("CallSid", "")
    call_status = form_data.get("CallStatus", "")
    duration = form_data.get("CallDuration", "0")
    answered_by = form_data.get("AnsweredBy", "")

    logger.info(f"Dialer status: session={session_id}, task={task_id}, status={call_status}")

    if session_id and task_id:
        try:
            engine = DialerEngine(db, current_user.id if current_user else 0)
            engine.handle_call_status(
                session_id=session_id,
                task_id=task_id,
                call_sid=call_sid,
                status=call_status,
                duration=int(duration) if duration else 0,
                answered_by=answered_by
            )
        except Exception as e:
            logger.error(f"Error handling call status: {e}")

    return {"success": True}


@router.post("/webhook/dial-status")
async def webhook_dial_status(
    request: Request,
    session_id: Optional[int] = None,
    task_id: Optional[int] = None
):
    """
    Dial action callback - called when the <Dial> verb completes.

    This is different from status callback - it's called when the actual
    dial attempt finishes (answered, busy, no-answer, etc.)
    """
    form_data = await request.form()
    dial_call_status = form_data.get("DialCallStatus", "")
    dial_call_duration = form_data.get("DialCallDuration", "0")

    logger.info(f"Dial completed: session={session_id}, task={task_id}, status={dial_call_status}")

    # Return TwiML to hang up after dial completes
    twiml = """<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Hangup/>
</Response>"""

    return Response(content=twiml, media_type="application/xml")
