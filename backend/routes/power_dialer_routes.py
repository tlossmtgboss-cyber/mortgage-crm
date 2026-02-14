"""
Power Dialer API Routes

Extracted from main.py - Power Dialer functionality including:
- Dialer settings management
- Click-to-dial calling
- Session management (create, pause, resume, stop)
- Compliance checking and DNC list management
- Call task and contact querying
- Call logs
- WebSocket for real-time updates
"""

from datetime import datetime
from typing import List, Optional
import logging

from fastapi import APIRouter, Depends, HTTPException, Request, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from sqlalchemy import or_, text
from sqlalchemy.orm import Session

from db import get_db
from telephony.provider import get_telephony_provider
from telephony.dialer_engine import DialerEngine, click_to_dial
from telephony.compliance import ComplianceChecker
from utils.websocket_auth import authenticate_websocket
from telephony.websocket import ws_manager

logger = logging.getLogger(__name__)


def _extract_token(request) -> str:
    """Extract Bearer token from Authorization header."""
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:]
    from fastapi import HTTPException
    raise HTTPException(status_code=401, detail="Not authenticated")


router = APIRouter(prefix="/api/v1", tags=["Power Dialer"])


# =============================================================================
# Pydantic Models
# =============================================================================

class DialerSessionCreate(BaseModel):
    """Request to create a new dialer session"""
    task_ids: List[int]


class ClickToDialRequest(BaseModel):
    """Request for single click-to-dial call"""
    phone_number: str
    contact_name: str
    lead_id: Optional[int] = None
    loan_id: Optional[int] = None
    task_id: Optional[int] = None


class DispositionRequest(BaseModel):
    """Request to set call disposition"""
    disposition: str
    notes: Optional[str] = None
    schedule_callback: Optional[datetime] = None


class TelephonySettingsUpdate(BaseModel):
    """Update agent telephony settings"""
    cell_phone: Optional[str] = None
    business_caller_id: Optional[str] = None
    dialer_enabled: Optional[bool] = None
    max_calls_per_day: Optional[int] = None
    auto_advance: Optional[bool] = None
    pause_between_calls: Optional[int] = None


class VerifyCallerIdRequest(BaseModel):
    """Request to verify a caller ID"""
    phone_number: str
    friendly_name: str


# =============================================================================
# Dialer Settings Endpoints
# =============================================================================

@router.get("/dialer/settings")
async def get_dialer_settings(
    request: Request,
    db: Session = Depends(get_db)
):
    """Get agent telephony settings"""
    import main

    # Get current user from main's dependency
    current_user = await main.get_current_user_flexible(request, db)

    try:
        settings = db.query(main.AgentTelephonySettings).filter(
            main.AgentTelephonySettings.user_id == current_user.id
        ).first()

        if not settings:
            return {
                "cell_phone": None,
                "business_caller_id": None,
                "dialer_enabled": False,
                "max_calls_per_day": 100,
                "auto_advance": True,
                "pause_between_calls": 3
            }

        return {
            "cell_phone": settings.cell_phone,
            "business_caller_id": settings.business_caller_id,
            "dialer_enabled": settings.dialer_enabled,
            "max_calls_per_day": settings.max_calls_per_day,
            "auto_advance": getattr(settings, 'auto_advance', True),
            "pause_between_calls": getattr(settings, 'pause_between_calls', 3)
        }
    except Exception as e:
        logger.error(f"Error getting dialer settings: {e}")
        return {
            "cell_phone": None,
            "business_caller_id": None,
            "dialer_enabled": False,
            "max_calls_per_day": 100,
            "auto_advance": True,
            "pause_between_calls": 3
        }


@router.put("/dialer/settings")
async def update_dialer_settings(
    data: TelephonySettingsUpdate,
    request: Request,
    db: Session = Depends(get_db)
):
    """Update agent telephony settings"""
    import main

    current_user = await main.get_current_user_flexible(request, db)

    try:
        # Ensure all telephony tables exist (for fresh deployments)
        try:
            db.execute(text("""
                CREATE TABLE IF NOT EXISTS agent_telephony_settings (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER UNIQUE NOT NULL REFERENCES users(id),
                    cell_phone VARCHAR,
                    business_caller_id VARCHAR,
                    dialer_enabled BOOLEAN DEFAULT TRUE,
                    max_calls_per_day INTEGER DEFAULT 200,
                    max_concurrent_sessions INTEGER DEFAULT 1,
                    auto_advance BOOLEAN DEFAULT TRUE,
                    pause_between_calls INTEGER DEFAULT 3,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS contact_dnc_status (
                    id SERIAL PRIMARY KEY,
                    phone_number VARCHAR UNIQUE NOT NULL,
                    reason VARCHAR,
                    added_by_id INTEGER REFERENCES users(id),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                DROP TABLE IF EXISTS active_calls;
                CREATE TABLE active_calls (
                    id SERIAL PRIMARY KEY,
                    contact_phone VARCHAR NOT NULL,
                    agent_id INTEGER REFERENCES users(id),
                    call_sid VARCHAR,
                    locked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    expires_at TIMESTAMP NOT NULL
                );
                CREATE TABLE IF NOT EXISTS call_logs (
                    id SERIAL PRIMARY KEY,
                    agent_id INTEGER REFERENCES users(id),
                    contact_phone VARCHAR NOT NULL,
                    contact_name VARCHAR,
                    lead_id INTEGER,
                    loan_id INTEGER,
                    referral_partner_id INTEGER,
                    mum_client_id INTEGER,
                    session_id INTEGER,
                    session_task_id INTEGER,
                    call_sid VARCHAR,
                    caller_id_used VARCHAR,
                    start_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    end_time TIMESTAMP,
                    duration_seconds INTEGER,
                    outcome VARCHAR,
                    failure_reason VARCHAR,
                    disposition VARCHAR,
                    notes TEXT,
                    ai_note_summary TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                -- Add missing columns to existing call_logs table
                ALTER TABLE call_logs ADD COLUMN IF NOT EXISTS referral_partner_id INTEGER;
                ALTER TABLE call_logs ADD COLUMN IF NOT EXISTS mum_client_id INTEGER;
                ALTER TABLE call_logs ADD COLUMN IF NOT EXISTS session_id INTEGER;
                ALTER TABLE call_logs ADD COLUMN IF NOT EXISTS session_task_id INTEGER;
                ALTER TABLE call_logs ADD COLUMN IF NOT EXISTS caller_id_used VARCHAR;
                ALTER TABLE call_logs ADD COLUMN IF NOT EXISTS start_time TIMESTAMP;
                ALTER TABLE call_logs ADD COLUMN IF NOT EXISTS end_time TIMESTAMP;
                ALTER TABLE call_logs ADD COLUMN IF NOT EXISTS failure_reason VARCHAR;
                ALTER TABLE call_logs ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            """))
            db.commit()
        except Exception as table_err:
            logger.debug(f"Table creation note: {table_err}")
            db.rollback()

        settings = db.query(main.AgentTelephonySettings).filter(
            main.AgentTelephonySettings.user_id == current_user.id
        ).first()

        if not settings:
            settings = main.AgentTelephonySettings(user_id=current_user.id)
            db.add(settings)

        if data.cell_phone is not None:
            settings.cell_phone = data.cell_phone
        if data.business_caller_id is not None:
            settings.business_caller_id = data.business_caller_id
        if data.dialer_enabled is not None:
            settings.dialer_enabled = data.dialer_enabled
        if data.max_calls_per_day is not None:
            settings.max_calls_per_day = data.max_calls_per_day
        if data.auto_advance is not None:
            settings.auto_advance = data.auto_advance
        if data.pause_between_calls is not None:
            settings.pause_between_calls = data.pause_between_calls

        db.commit()
        return {"success": True, "message": "Settings updated"}
    except Exception as e:
        logger.error(f"Error updating dialer settings: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Failed to update settings")


# =============================================================================
# Caller ID Verification Endpoints
# =============================================================================

@router.post("/dialer/verify-caller-id")
async def verify_caller_id(
    data: VerifyCallerIdRequest,
    request: Request,
    db: Session = Depends(get_db)
):
    """Start caller ID verification process"""
    import main

    current_user = await main.get_current_user_flexible(request, db)

    provider = get_telephony_provider()
    result = provider.verify_caller_id(data.phone_number, data.friendly_name)

    if result.get("success"):
        # Store verification attempt
        verified = main.VerifiedCallerId(
            user_id=current_user.id,
            phone_number=data.phone_number,
            friendly_name=data.friendly_name,
            verification_status="pending"
        )
        db.add(verified)
        db.commit()

    return result


@router.get("/dialer/verified-caller-ids")
async def list_verified_caller_ids(
    request: Request,
    db: Session = Depends(get_db)
):
    """List all verified caller IDs"""
    import main

    current_user = await main.get_current_user_flexible(request, db)

    provider = get_telephony_provider()
    return provider.list_verified_caller_ids()


# =============================================================================
# Click-to-Dial Endpoints
# =============================================================================

@router.post("/dialer/click-to-dial")
async def api_click_to_dial(
    data: ClickToDialRequest,
    request: Request,
    db: Session = Depends(get_db)
):
    """Single click-to-dial call"""
    import main

    current_user = await main.get_current_user_flexible(request, db)

    try:
        base_url = str(request.base_url).rstrip("/")
        logger.info(f"Click-to-dial: {data.phone_number} for user {current_user.id}, base_url={base_url}")

        result = click_to_dial(
            db_session=db,
            agent_id=current_user.id,
            phone_number=data.phone_number,
            contact_name=data.contact_name,
            base_url=base_url,
            lead_id=data.lead_id,
            loan_id=data.loan_id,
            task_id=data.task_id
        )

        if not result.get("success"):
            logger.warning(f"Click-to-dial failed: {result}")
            raise HTTPException(status_code=400, detail=result.get("error"))

        logger.info(f"Click-to-dial success: {result}")
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Click-to-dial error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Click-to-dial failed")


# =============================================================================
# Session Management Endpoints
# =============================================================================

@router.post("/dialer/sessions")
async def create_dialer_session(
    data: DialerSessionCreate,
    request: Request,
    db: Session = Depends(get_db)
):
    """Create a new power dialer session"""
    import main

    current_user = await main.get_current_user_flexible(request, db)

    base_url = str(request.base_url).rstrip("/")

    engine = DialerEngine(db, current_user.id)
    result = engine.create_session(data.task_ids, base_url)

    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error"))

    return result


@router.get("/dialer/sessions/active")
async def get_active_session(
    request: Request,
    db: Session = Depends(get_db)
):
    """Get agent's active dialer session if any"""
    import main

    current_user = await main.get_current_user_flexible(request, db)

    session = db.query(main.DialerSession).filter(
        main.DialerSession.agent_id == current_user.id,
        main.DialerSession.status.in_([main.DialerSessionStatus.ACTIVE, main.DialerSessionStatus.PAUSED])
    ).first()

    if not session:
        return {"active_session": None}

    engine = DialerEngine(db, current_user.id)
    return {"active_session": engine.get_session_status(session.id)}


@router.get("/dialer/sessions/{session_id}")
async def get_session_status(
    session_id: int,
    request: Request,
    db: Session = Depends(get_db)
):
    """Get status of a specific session"""
    import main

    current_user = await main.get_current_user_flexible(request, db)

    engine = DialerEngine(db, current_user.id)
    status = engine.get_session_status(session_id)

    if not status:
        raise HTTPException(status_code=404, detail="Session not found")

    return status


@router.get("/dialer/sessions/{session_id}/next-task")
async def get_next_dialer_task(
    session_id: int,
    request: Request,
    db: Session = Depends(get_db)
):
    """Get the next task in the session queue"""
    import main

    current_user = await main.get_current_user_flexible(request, db)

    engine = DialerEngine(db, current_user.id)
    task = engine.get_next_task(session_id)

    if not task:
        return {"next_task": None, "message": "No more tasks in queue"}

    return {"next_task": task}


@router.post("/dialer/sessions/{session_id}/call/{task_id}")
async def initiate_session_call(
    session_id: int,
    task_id: int,
    request: Request,
    db: Session = Depends(get_db)
):
    """Initiate call for a specific task in the session"""
    import main

    current_user = await main.get_current_user_flexible(request, db)

    base_url = str(request.base_url).rstrip("/")

    engine = DialerEngine(db, current_user.id)
    result = engine.initiate_call(session_id, task_id, base_url)

    if not result.get("success"):
        if result.get("skipped"):
            return result  # Compliance skip is not an error
        raise HTTPException(status_code=400, detail=result.get("error"))

    return result


@router.post("/dialer/sessions/{session_id}/tasks/{task_id}/disposition")
async def set_task_disposition(
    session_id: int,
    task_id: int,
    data: DispositionRequest,
    request: Request,
    db: Session = Depends(get_db)
):
    """Set disposition for a completed call"""
    import main

    current_user = await main.get_current_user_flexible(request, db)

    engine = DialerEngine(db, current_user.id)
    result = engine.set_disposition(
        session_id=session_id,
        task_id=task_id,
        disposition=data.disposition,
        notes=data.notes,
        schedule_callback=data.schedule_callback
    )

    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error"))

    return result


@router.post("/dialer/sessions/{session_id}/tasks/{task_id}/skip")
async def skip_session_task(
    session_id: int,
    task_id: int,
    request: Request,
    reason: str = "manual_skip",
    db: Session = Depends(get_db)
):
    """Skip a task in the session"""
    import main

    current_user = await main.get_current_user_flexible(request, db)

    engine = DialerEngine(db, current_user.id)
    result = engine.skip_task(session_id, task_id, reason)

    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error"))

    return result


@router.post("/dialer/sessions/{session_id}/pause")
async def pause_session(
    session_id: int,
    request: Request,
    db: Session = Depends(get_db)
):
    """Pause the dialer session"""
    import main

    current_user = await main.get_current_user_flexible(request, db)

    engine = DialerEngine(db, current_user.id)
    result = engine.pause_session(session_id)

    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error"))

    return result


@router.post("/dialer/sessions/{session_id}/resume")
async def resume_session(
    session_id: int,
    request: Request,
    db: Session = Depends(get_db)
):
    """Resume a paused session"""
    import main

    current_user = await main.get_current_user_flexible(request, db)

    engine = DialerEngine(db, current_user.id)
    result = engine.resume_session(session_id)

    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error"))

    return result


@router.post("/dialer/sessions/{session_id}/stop")
async def stop_session(
    session_id: int,
    request: Request,
    db: Session = Depends(get_db)
):
    """Stop the dialer session"""
    import main

    current_user = await main.get_current_user_flexible(request, db)

    engine = DialerEngine(db, current_user.id)
    result = engine.stop_session(session_id)

    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error"))

    return result


# =============================================================================
# Compliance Endpoints
# =============================================================================

@router.get("/dialer/compliance/check")
async def check_compliance(
    phone_number: str,
    request: Request,
    db: Session = Depends(get_db)
):
    """Check compliance status for a phone number"""
    import main

    current_user = await main.get_current_user_flexible(request, db)

    compliance = ComplianceChecker(db)
    result = compliance.full_compliance_check(phone_number, current_user.id)
    return result


@router.post("/dialer/dnc/add")
async def add_to_dnc(
    phone_number: str,
    request: Request,
    reason: str = "customer_request",
    db: Session = Depends(get_db)
):
    """Add a phone number to the Do Not Call list"""
    import main

    current_user = await main.get_current_user_flexible(request, db)

    compliance = ComplianceChecker(db)
    success = compliance.add_to_dnc(phone_number, reason, current_user.id)

    if not success:
        raise HTTPException(status_code=500, detail="Failed to add to DNC list")

    return {"success": True, "message": f"{phone_number} added to DNC list"}


@router.delete("/dialer/dnc/{phone_number}")
async def remove_from_dnc(
    phone_number: str,
    request: Request,
    db: Session = Depends(get_db)
):
    """Remove a phone number from the Do Not Call list"""
    import main

    current_user = await main.get_current_user_flexible(request, db)

    compliance = ComplianceChecker(db)
    success = compliance.remove_from_dnc(phone_number)

    return {"success": success, "message": f"{phone_number} removed from DNC list" if success else "Number not found in DNC list"}


# =============================================================================
# Call Tasks and Contacts Endpoints
# =============================================================================

@router.get("/dialer/call-tasks-debug")
async def get_dialer_call_tasks_debug(
    db: Session = Depends(get_db)
):
    """Debug endpoint to test AITask query without auth."""
    import main

    try:
        # Test basic count
        count = db.query(main.AITask).count()

        # Test the exact filter query used in call-tasks
        call_tasks = db.query(main.AITask).filter(
            or_(
                main.AITask.type == None,
                main.AITask.type != main.TaskType.COMPLETED
            ),
            or_(
                main.AITask.title.ilike('%call%'),
                main.AITask.title.ilike('%phone%'),
                main.AITask.title.ilike('%contact%'),
                main.AITask.title.ilike('%voicemail%'),
                main.AITask.title.ilike('%dial%'),
                main.AITask.title.ilike('%reach out%')
            )
        ).limit(5).all()

        results = []
        for t in call_tasks:
            results.append({
                "id": t.id,
                "title": t.title,
                "type": t.type.value if t.type else None
            })

        return {"debug": True, "total_aitasks": count, "filtered_count": len(call_tasks), "sample": results}
    except Exception as e:
        import traceback
        return {"debug": True, "error": "Internal server error"}


@router.get("/dialer/call-tasks")
async def get_dialer_call_tasks(
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Get all call-related tasks for the Power Dialer.
    Returns tasks with 'call', 'phone', 'contact', etc. in the title.
    Uses AITask model which has type, borrower_name fields.
    """
    import main

    current_user = await main.get_current_user(_extract_token(request), request, db)

    # Immediate logging to confirm we entered the endpoint
    logger.info(f"[CALL-TASKS] Endpoint entered, user_id={current_user.id if current_user else 'None'}")
    try:
        logger.info("[CALL-TASKS] Starting query...")
        # Query AITask model (not Task) which has the correct fields
        # Handle null type values by using or_ with is_(None)
        call_tasks = db.query(main.AITask).filter(
            or_(
                main.AITask.type == None,
                main.AITask.type != main.TaskType.COMPLETED
            ),
            or_(
                main.AITask.title.ilike('%call%'),
                main.AITask.title.ilike('%phone%'),
                main.AITask.title.ilike('%contact%'),
                main.AITask.title.ilike('%voicemail%'),
                main.AITask.title.ilike('%dial%'),
                main.AITask.title.ilike('%reach out%')
            )
        ).order_by(main.AITask.due_date.asc().nulls_last(), main.AITask.created_at.desc()).limit(100).all()

        logger.info(f"[CALL-TASKS] Query returned {len(call_tasks)} tasks")

        tasks = []
        for task in call_tasks:
            try:
                # Get contact info and phone
                contact_name = task.borrower_name or 'Unknown'
                phone_number = ''
                entity_type = None

                if task.loan_id:
                    entity_type = "loan"
                    loan = db.query(main.Loan).filter(main.Loan.id == task.loan_id).first()
                    if loan:
                        contact_name = contact_name if contact_name != 'Unknown' else (loan.borrower_name or 'Unknown')
                        phone_number = loan.borrower_phone or ''
                elif task.lead_id:
                    entity_type = "lead"
                    lead = db.query(main.Lead).filter(main.Lead.id == task.lead_id).first()
                    if lead:
                        contact_name = contact_name if contact_name != 'Unknown' else (lead.name or 'Unknown')
                        phone_number = lead.phone or ''

                tasks.append({
                    "id": task.id,
                    "title": task.title,
                    "description": task.description,
                    "priority": task.priority,
                    "status": task.type.value if task.type else "In Progress",
                    "due_date": task.due_date.isoformat() if task.due_date else None,
                    "entity_type": entity_type,
                    "loan_id": task.loan_id,
                    "lead_id": task.lead_id,
                    "created_at": task.created_at.isoformat() if task.created_at else None,
                    "contact_name": contact_name,
                    "phone_number": phone_number
                })
            except Exception as task_err:
                logger.warning(f"Error processing task {task.id}: {task_err}")
                continue

        logger.info(f"[CALL-TASKS] Returning {len(tasks)} processed tasks")
        return {"tasks": tasks, "total": len(tasks)}
    except Exception as e:
        logger.error(f"Error fetching call tasks: {e}")
        import traceback
        traceback.print_exc()
        # Return 200 with error info so we can debug
        return {"tasks": [], "total": 0, "error": "Internal server error"}


@router.get("/dialer/callable-contacts")
async def get_callable_contacts(
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Get all contacts (leads and loans) that have phone numbers for dialing.
    """
    import main

    current_user = await main.get_current_user_flexible(request, db)

    try:
        contacts = []

        # Get leads with phone numbers
        leads_query = db.execute(text("""
            SELECT id, name, phone, email, CAST(status AS TEXT) as status, created_at
            FROM leads
            WHERE phone IS NOT NULL AND phone != ''
            AND CAST(status AS TEXT) NOT IN ('closed', 'dead', 'withdrawn', 'converted')
            ORDER BY created_at DESC
            LIMIT 100
        """)).mappings().all()

        for row in leads_query:
            phone = row.get('phone') or ''
            if phone and len(phone) >= 10:
                contacts.append({
                    "id": f"lead_{row.get('id')}",
                    "type": "lead",
                    "name": row.get('name') or "Unknown Lead",
                    "phone_number": phone,
                    "email": row.get('email'),
                    "status": row.get('status'),
                    "entity_id": row.get('id')
                })

        # Get loans with borrower phone numbers
        loans_query = db.execute(text("""
            SELECT id, borrower_name, borrower_phone, borrower_email,
                   CAST(stage AS TEXT) as stage, created_at
            FROM loans
            WHERE borrower_phone IS NOT NULL AND borrower_phone != ''
            AND CAST(stage AS TEXT) NOT IN ('funded', 'withdrawn', 'dead', 'closed')
            ORDER BY created_at DESC
            LIMIT 100
        """)).mappings().all()

        for row in loans_query:
            phone = row.get('borrower_phone') or ''
            if phone and len(phone) >= 10:
                contacts.append({
                    "id": f"loan_{row.get('id')}",
                    "type": "loan",
                    "name": row.get('borrower_name') or "Unknown Borrower",
                    "phone_number": phone,
                    "email": row.get('borrower_email'),
                    "status": row.get('stage'),
                    "entity_id": row.get('id')
                })

        return {"contacts": contacts, "total": len(contacts)}
    except Exception as e:
        logger.error(f"Error fetching callable contacts: {e}")
        return {"contacts": [], "total": 0, "error": "Internal server error"}


@router.get("/dialer/call-logs")
async def get_call_logs(
    request: Request,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db)
):
    """Get call history for the agent"""
    import main

    current_user = await main.get_current_user_flexible(request, db)

    logs = db.query(main.CallLog).filter(
        main.CallLog.agent_id == current_user.id
    ).order_by(main.CallLog.created_at.desc()).offset(offset).limit(limit).all()

    return {
        "call_logs": [{
            "id": log.id,
            "contact_phone": log.contact_phone,
            "contact_name": log.contact_name,
            "direction": log.direction,
            "duration_seconds": log.duration_seconds,
            "outcome": log.outcome,
            "disposition": log.disposition,
            "notes": log.notes,
            "started_at": log.started_at.isoformat() if log.started_at else None,
            "ended_at": log.ended_at.isoformat() if log.ended_at else None,
            "lead_id": log.lead_id,
            "loan_id": log.loan_id
        } for log in logs]
    }


# =============================================================================
# WebSocket Endpoint for Real-Time Dialer Updates
# =============================================================================

@router.websocket("/dialer/ws/{agent_id}")
async def websocket_dialer(websocket: WebSocket, agent_id: str):
    """
    WebSocket connection for real-time dialer updates.
    Requires JWT authentication.

    Clients should connect with their agent_id to receive:
    - Call status updates (ringing, answered, completed)
    - Session progress updates
    - Disposition prompts
    - Error notifications
    """
    await websocket.accept()

    # Authenticate
    db = next(get_db())
    try:
        user, auth_error = authenticate_websocket(websocket, db)
        if not user:
            await websocket.send_json({"type": "error", "message": auth_error or "Authentication required"})
            await websocket.close(code=4001, reason="Authentication required")
            return
    finally:
        db.close()

    await ws_manager.connect(websocket, agent_id, skip_accept=True)
    try:
        while True:
            # Keep connection alive, handle incoming messages
            data = await websocket.receive_text()

            # Handle ping/pong for connection keepalive
            if data == "ping":
                await websocket.send_text("pong")
            else:
                # Echo back acknowledgment for other messages
                await websocket.send_json({"type": "ack", "message": data})
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket, agent_id)
        logger.info(f"WebSocket disconnected for agent {agent_id}")
    except Exception as e:
        logger.error(f"WebSocket error for agent {agent_id}: {e}")
        ws_manager.disconnect(websocket, agent_id)


@router.get("/dialer/ws/status")
async def websocket_status():
    """Get WebSocket connection status for monitoring"""
    return {
        "connected_agents": ws_manager.get_connected_agents(),
        "total_connections": sum(len(conns) for conns in ws_manager.active_connections.values())
    }
